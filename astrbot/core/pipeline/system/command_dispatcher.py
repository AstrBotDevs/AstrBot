from __future__ import annotations

import traceback
from typing import TYPE_CHECKING, Any

from astrbot.core import logger
from astrbot.core.message.message_event_result import MessageChain, MessageEventResult
from astrbot.core.pipeline.system.star_yield import StarHandlerAdapter, StarYieldDriver
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import (
    EventType,
    StarHandlerMetadata,
    star_handlers_registry,
)

if TYPE_CHECKING:
    from astrbot.core.config import AstrBotConfig
    from astrbot.core.pipeline.agent.executor import AgentExecutor
    from astrbot.core.pipeline.engine.send_service import SendService
    from astrbot.core.platform.astr_message_event import AstrMessageEvent


class CommandDispatcher:
    def __init__(
        self,
        config: AstrBotConfig,
        send_service: SendService,
        agent_executor: AgentExecutor | None = None,
    ) -> None:
        self._config = config
        self._send_service = send_service
        self._agent_executor = agent_executor

        # 初始化 yield 驱动器
        self._yield_driver = StarYieldDriver(
            self._send_message,
        )
        self._handler_adapter = StarHandlerAdapter(self._yield_driver)

        # 配置
        self._no_permission_reply = config.get("platform_settings", {}).get(
            "no_permission_reply", True
        )
        self._disable_builtin = config.get("disable_builtin_commands", False)

    async def _send_message(self, event: AstrMessageEvent) -> None:
        """发送消息回调"""
        if event.get_result():
            await self._send_service.send(event)

    async def _handle_provider_request(
        self,
        event: AstrMessageEvent,
    ) -> None:
        """收到 ProviderRequest 时立即执行 Agent 并发送结果"""
        if not self._agent_executor:
            return
        await self._agent_executor.run(event)
        await self._send_service.send(event)
        event.set_extra("_provider_request_consumed", True)
        event.set_extra("provider_request", None)
        event.set_extra("has_provider_request", False)

    async def match(
        self,
        event: AstrMessageEvent,
        plugins_name: list[str] | None = None,
    ) -> list[tuple[StarHandlerMetadata, dict[str, Any]]]:
        """仅匹配命令，不执行

        用于在系统机制检查之前确定是否有命令匹配，并设置 is_wake 标志。
        匹配结果应传递给 execute() 方法在系统机制检查之后执行。

        Args:
            event: 消息事件
            plugins_name: 启用的插件列表（None 表示全部）

        Returns:
            匹配的 handler 列表 [(handler, parsed_params), ...]
        """
        return await self._match_handlers(event, plugins_name)

    async def execute(
        self,
        event: AstrMessageEvent,
        matched_handlers: list[tuple[StarHandlerMetadata, dict[str, Any]]],
    ) -> bool:
        """执行已匹配的命令

        应在系统机制检查（限流、权限等）之后调用。

        Args:
            event: 消息事件
            matched_handlers: match() 返回的匹配结果

        Returns:
            bool: 是否有命令被执行
        """
        if not matched_handlers:
            return False

        for handler, parsed_params in matched_handlers:
            plugin_meta = star_map.get(handler.handler_module_path)
            if not plugin_meta:
                logger.warning(
                    f"Plugin not found for handler: {handler.handler_module_path}"
                )
                continue

            logger.debug(f"Dispatching to {plugin_meta.name}.{handler.handler_name}")

            try:
                # 使用适配器调用，完整支持 yield
                result = await self._handler_adapter.invoke(
                    handler.handler,
                    event,
                    **parsed_params,
                )

                if result.error:
                    # handler 执行出错
                    if event.is_at_or_wake_command:
                        error_msg = (
                            f":(\n\n调用插件 {plugin_meta.name} 的 "
                            f"{handler.handler_name} 时出现异常：{result.error}"
                        )
                        event.set_result(MessageEventResult().message(error_msg))
                    event.stop_event()
                    return True

                # 检查是否有 LLM 请求
                if result.llm_requests and not event.get_extra(
                    "_provider_request_consumed",
                    False,
                ):
                    event.set_extra("has_provider_request", True)

                if result.stopped or event.is_stopped():
                    return True

            except Exception as e:
                logger.error(f"Dispatch error: {e}")
                logger.error(traceback.format_exc())
                event.stop_event()
                return True

        return len(matched_handlers) > 0

    async def _match_handlers(
        self,
        event: AstrMessageEvent,
        plugins_name: list[str] | None,
    ) -> list[tuple[StarHandlerMetadata, dict[str, Any]]]:
        """匹配所有适用的 handler

        Returns:
            [(handler, parsed_params), ...]
        """
        matched: list[tuple[StarHandlerMetadata, dict[str, Any]]] = []

        for handler in star_handlers_registry.get_handlers_by_event_type(
            EventType.AdapterMessageEvent,
            plugins_name=plugins_name,
        ):
            # 跳过内置命令（如配置）
            if (
                self._disable_builtin
                and handler.handler_module_path
                == "astrbot.builtin_stars.builtin_commands.main"
            ):
                continue

            # 必须有过滤器
            if not handler.event_filters:
                continue

            # 应用过滤器
            passed = True
            permission_failed = False
            permission_raise_error = False
            parsed_params: dict[str, Any] = {}

            for f in handler.event_filters:
                try:
                    from astrbot.core.star.filter.permission import PermissionTypeFilter

                    if isinstance(f, PermissionTypeFilter):
                        if not f.filter(event, self._config):
                            permission_failed = True
                            permission_raise_error = f.raise_error
                    elif not f.filter(event, self._config):
                        passed = False
                        break
                except Exception as e:
                    # 过滤器执行出错 — 发送错误消息并停止
                    plugin_meta = star_map.get(handler.handler_module_path)
                    plugin_name = plugin_meta.name if plugin_meta else "unknown"
                    await event.send(
                        MessageEventResult().message(f"插件 {plugin_name}: {e}")
                    )
                    event.stop_event()
                    passed = False
                    break

                # 获取解析的参数
                if "parsed_params" in event.get_extra(default={}):
                    parsed_params = event.get_extra("parsed_params")
                    event._extras.pop("parsed_params", None)

            if not passed:
                continue

            if permission_failed:
                if not permission_raise_error:
                    continue
                if self._no_permission_reply:
                    await self._handle_permission_denied(event, handler)
                event.stop_event()
                return []

            # 跳过 CommandGroup 的空 handler
            from astrbot.core.star.filter.command_group import CommandGroupFilter

            is_group_cmd = any(
                isinstance(f, CommandGroupFilter) for f in handler.event_filters
            )
            if not is_group_cmd:
                matched.append((handler, parsed_params))
                event.is_wake = True

        return matched

    @staticmethod
    async def _handle_permission_denied(
        event: AstrMessageEvent,
        handler: StarHandlerMetadata,
    ) -> None:
        """处理权限不足"""
        plugin_meta = star_map.get(handler.handler_module_path)
        plugin_name = plugin_meta.name if plugin_meta else "unknown"

        await event.send(
            MessageChain().message(
                f"您(ID: {event.get_sender_id()})的权限不足以使用此指令。"
                f"通过 /sid 获取 ID 并请管理员添加。"
            )
        )
        logger.info(
            f"触发 {plugin_name} 时, 用户(ID={event.get_sender_id()}) 权限不足。"
        )
