"""本地 Agent 模式的 AstrBot 插件调用 Stage"""

import traceback
from collections.abc import AsyncGenerator
from typing import Any

from astrbot.core import astrbot_config, logger
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import EventType, StarHandlerMetadata
from astrbot.core.utils.trace import _current_span

from ...context import PipelineContext, call_event_hook, call_handler
from ..stage import Stage


class StarRequestSubStage(Stage):
    async def initialize(self, ctx: PipelineContext) -> None:
        self.prompt_prefix = ctx.astrbot_config["provider_settings"]["prompt_prefix"]
        self.identifier = ctx.astrbot_config["provider_settings"]["identifier"]
        self.ctx = ctx

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> AsyncGenerator[Any, None]:
        activated_handlers: list[StarHandlerMetadata] = event.get_extra(
            "activated_handlers",
        )
        handlers_parsed_params: dict[str, dict[str, Any]] = event.get_extra(
            "handlers_parsed_params",
        )
        if not handlers_parsed_params:
            handlers_parsed_params = {}

        _trace_on = astrbot_config.get("trace_enable", False)

        for handler in activated_handlers:
            params = handlers_parsed_params.get(handler.handler_full_name, {})
            md = star_map.get(handler.handler_module_path)
            if not md:
                logger.warning(
                    f"Cannot find plugin for given handler module path: {handler.handler_module_path}",
                )
                continue
            logger.debug(f"plugin -> {md.name} - {handler.handler_name}")

            plugin_span = (
                (_current_span.get() or event.trace).child(
                    handler.handler_name, span_type="plugin_handler"
                )
                if _trace_on
                else None
            )
            if plugin_span is not None:
                plugin_span.set_meta(
                    plugin=md.name,
                    plugin_type="builtin" if md.reserved else "third_party",
                )
                plugin_span.set_input(command=handler.handler_full_name)

            # Set plugin_span as the current ContextVar span so that any
            # span_context / span_record calls inside the handler automatically
            # attach as children of this plugin_handler span.
            _plugin_span_token = (
                _current_span.set(plugin_span) if plugin_span is not None else None
            )

            try:
                wrapper = call_handler(event, handler.handler, **params)
                async for ret in wrapper:
                    yield ret
                event.clear_result()  # 清除上一个 handler 的结果
                if plugin_span is not None and plugin_span.finished_at is None:
                    plugin_span.set_output(has_result=event.get_result() is not None)
                    plugin_span.finish()
            except Exception as e:
                traceback_text = traceback.format_exc()
                logger.error(traceback_text)
                logger.error(f"Star {handler.handler_full_name} handle error: {e}")
                if plugin_span is not None and plugin_span.finished_at is None:
                    plugin_span.finish(status="error", error=str(e))

                await call_event_hook(
                    event,
                    EventType.OnPluginErrorEvent,
                    md.name,
                    handler.handler_name,
                    e,
                    traceback_text,
                )

                if not event.is_stopped() and event.is_at_or_wake_command:
                    ret = f":(\n\n在调用插件 {md.name} 的处理函数 {handler.handler_name} 时出现异常：{e}"
                    event.set_result(MessageEventResult().message(ret))
                    yield
                    event.clear_result()

                event.stop_event()
            finally:
                # Reset ContextVar to the span active before this handler
                if _plugin_span_token is not None:
                    _current_span.reset(_plugin_span_token)
