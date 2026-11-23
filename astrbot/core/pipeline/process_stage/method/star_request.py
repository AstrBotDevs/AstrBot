"""本地 Agent 模式的 AstrBot 插件调用 Stage"""

import traceback
from collections.abc import AsyncGenerator
from typing import Any

from astrbot.core import logger
from astrbot.core.i18n import get_config_locale, translate
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.pipeline.context import PipelineContext, call_event_hook, call_handler
from astrbot.core.pipeline.stage import Stage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.filter.regex import RegexFilter
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import EventType, StarHandlerMetadata


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
            # Match the component categories used by the plugin detail page.
            handler_category = (
                "command"
                if any(
                    isinstance(
                        event_filter, CommandFilter | CommandGroupFilter | RegexFilter
                    )
                    for event_filter in handler.event_filters
                )
                else "listener"
            )
            event.trace.record(
                "handler_start",
                kind="plugin_handler",
                status="running",
                plugin=md.name or handler.handler_module_path,
                plugin_display_name=md.display_name or md.name,
                handler=handler.handler_name,
                handler_full_name=handler.handler_full_name,
                handler_type=handler.event_type.name,
                handler_category=handler_category,
                priority=handler.extras_configs.get("priority", 0),
            )
            try:
                wrapper = call_handler(event, handler.handler, **params)
                async for ret in wrapper:
                    yield ret
                event.trace.record(
                    "handler_end",
                    kind="plugin_handler",
                    status="success",
                    plugin=md.name or handler.handler_module_path,
                    plugin_display_name=md.display_name or md.name,
                    handler=handler.handler_name,
                    handler_full_name=handler.handler_full_name,
                    handler_type=handler.event_type.name,
                    handler_category=handler_category,
                )
                if event.is_stopped():
                    break
                event.clear_result()  # 清除上一个 handler 的结果
            except Exception as e:
                if event.get_ui_interaction() is not None:
                    event.set_extra(
                        "ui_action_error",
                        {
                            "code": "INVALID_INPUT"
                            if type(e).__name__ == "ValidationError"
                            else "ACTION_FAILED",
                            "message": "Invalid action input."
                            if type(e).__name__ == "ValidationError"
                            else "The plugin action failed.",
                        },
                    )
                traceback_text = traceback.format_exc()
                plugin_name = md.name or handler.handler_module_path
                # Keep handler failures on the plugin's side of the log filter.
                logger.error(
                    traceback_text,
                    extra={"plugin_name": plugin_name},
                )
                logger.error(
                    f"Star {handler.handler_full_name} handle error: {e}",
                    extra={"plugin_name": plugin_name},
                )
                event.trace.record(
                    "handler_end",
                    kind="plugin_handler",
                    status="error",
                    plugin=md.name or handler.handler_module_path,
                    plugin_display_name=md.display_name or md.name,
                    handler=handler.handler_name,
                    handler_full_name=handler.handler_full_name,
                    handler_type=handler.event_type.name,
                    handler_category=handler_category,
                    error=str(e),
                )

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
                    ret = translate(
                        "plugin_handler_error",
                        get_config_locale(self.ctx.astrbot_config),
                        plugin=md.name,
                        handler=handler.handler_name,
                        detail=str(e),
                    )
                    event.set_result(MessageEventResult().message(ret))
                    yield None
                    event.clear_result()

                event.stop_event()
