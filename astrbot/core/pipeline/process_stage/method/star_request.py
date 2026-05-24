"""本地 Agent 模式的 AstrBot 插件调用 Stage"""

import traceback
from collections.abc import AsyncGenerator
from typing import Any

from astrbot.core import astrbot_config, logger
from astrbot.core.i18n import t
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.pipeline.context import PipelineContext, call_event_hook, call_handler
from astrbot.core.pipeline.process_stage.stage import Stage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import EventType, StarHandlerMetadata
from astrbot.core.utils.trace import _current_span


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
            if event.is_stopped():
                break
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
                if event.is_stopped():
                    break
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
                sdk_plugin_bridge = getattr(
                    self.ctx.plugin_manager.context,
                    "sdk_plugin_bridge",
                    None,
                )
                if sdk_plugin_bridge is not None:
                    try:
                        await sdk_plugin_bridge.dispatch_message_event(
                            "plugin_error",
                            event,
                            {
                                "plugin_name": md.name,
                                "handler_name": handler.handler_name,
                                "error": str(e),
                                "traceback": traceback_text,
                            },
                        )
                    except Exception as exc:
                        logger.warning("SDK plugin_error dispatch failed: %s", exc)

                if not event.is_stopped() and event.is_at_or_wake_command:
                    ret = t(
                        "pipeline.plugin_handler_error",
                        locale=self.ctx.get_current_language(),
                        plugin_name=md.name,
                        handler_name=handler.handler_name,
                        error=e,
                    )
                    event.set_result(MessageEventResult().message(ret))
                    yield None
                    event.clear_result()

                event.stop_event()
            finally:
                # Reset ContextVar to the span active before this handler
                if _plugin_span_token is not None:
                    _current_span.reset(_plugin_span_token)
