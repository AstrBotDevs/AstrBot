from collections.abc import AsyncGenerator

from astrbot.core import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.star_handler import StarHandlerMetadata

from ..context import PipelineContext
from ..stage import Stage, register_stage
from .method.agent_request import AgentRequestSubStage
from .method.star_request import StarRequestSubStage


@register_stage
class ProcessStage(Stage):
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.config = ctx.astrbot_config
        self.plugin_manager = ctx.plugin_manager
        self.sdk_plugin_bridge = getattr(
            ctx.plugin_manager.context, "sdk_plugin_bridge", None
        )

        # initialize agent sub stage
        self.agent_sub_stage = AgentRequestSubStage()
        await self.agent_sub_stage.initialize(ctx)

        # initialize star request sub stage
        self.star_request_sub_stage = StarRequestSubStage()
        await self.star_request_sub_stage.initialize(ctx)

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> None | AsyncGenerator[None, None]:
        """处理事件"""
        activated_handlers: list[StarHandlerMetadata] = event.get_extra(
            "activated_handlers",
        )
        if (
            activated_handlers
            and self.sdk_plugin_bridge is not None
            and not event.is_stopped()
            and (
                not hasattr(self.sdk_plugin_bridge, "has_active_sdk_command_handlers")
                or self.sdk_plugin_bridge.has_active_sdk_command_handlers()
            )
            and hasattr(self.sdk_plugin_bridge, "detect_legacy_command_conflict")
        ):
            # 新旧插件命令冲突时，SDK 插件优先：循环移除所有冲突的旧插件 handler
            removed_handler_names: set[str] = set()
            max_iterations = len(activated_handlers)
            iteration_count = 0
            while activated_handlers:
                iteration_count += 1
                if iteration_count > max_iterations:
                    logger.warning(
                        "Legacy command conflict filtering exceeded the handler count guard, aborting the conflict loop: remaining_handlers=%s",
                        len(activated_handlers),
                    )
                    break
                conflict = self.sdk_plugin_bridge.detect_legacy_command_conflict(
                    event,
                    activated_handlers,
                )
                if conflict is None:
                    break
                logger.warning(
                    "新旧插件命令冲突，SDK 插件优先: command=%s legacy_handler=%s sdk_handler=%s",
                    conflict.command_name,
                    conflict.legacy.handler_full_name,
                    conflict.sdk.handler_full_name,
                )
                target_handler_name = conflict.legacy.handler_full_name
                filtered_handlers: list[StarHandlerMetadata] = []
                removed_current_conflict = False
                for handler in activated_handlers:
                    handler_full_name = getattr(handler, "handler_full_name", None)
                    if handler_full_name == target_handler_name:
                        removed_current_conflict = True
                        removed_handler_names.add(target_handler_name)
                        continue
                    filtered_handlers.append(handler)
                if not removed_current_conflict:
                    logger.warning(
                        "Legacy command conflict matched an unknown handler, keeping legacy handler list unchanged: legacy_handler=%s sdk_handler=%s",
                        conflict.legacy.handler_full_name,
                        conflict.sdk.handler_full_name,
                    )
                    break
                activated_handlers = filtered_handlers
            if removed_handler_names:
                # 同步更新 event extras，确保下游 sub stage 看到过滤后的列表
                event.set_extra("activated_handlers", activated_handlers)
                # 清理已移除 handler 的解析参数
                handlers_parsed_params = event.get_extra("handlers_parsed_params")
                if isinstance(handlers_parsed_params, dict):
                    for name in removed_handler_names:
                        handlers_parsed_params.pop(name, None)

        # 有插件 Handler 被激活
        if activated_handlers:
            async for resp in self.star_request_sub_stage.process(event):
                # 生成器返回值处理
                if isinstance(resp, ProviderRequest):
                    # Handler 的 LLM 请求
                    event.set_extra("provider_request", resp)
                    _t = False
                    async for _ in self.agent_sub_stage.process(event):
                        _t = True
                        yield
                    if not _t:
                        yield
                else:
                    yield

        if self.sdk_plugin_bridge is not None and not event.is_stopped():
            sdk_result = await self.sdk_plugin_bridge.dispatch_message(event)
            if sdk_result.sent_message or sdk_result.stopped:
                yield

        # 调用 LLM 相关请求
        if not self.ctx.astrbot_config["provider_settings"].get("enable", True):
            return

        should_call_llm = (
            self.sdk_plugin_bridge.get_effective_should_call_llm(event)
            if self.sdk_plugin_bridge is not None
            and hasattr(self.sdk_plugin_bridge, "get_effective_should_call_llm")
            else not event.call_llm
        )
        effective_result = (
            self.sdk_plugin_bridge.get_effective_result(event)
            if self.sdk_plugin_bridge is not None
            and hasattr(self.sdk_plugin_bridge, "get_effective_result")
            else event.get_result()
        )
        if not event._has_send_oper and event.is_at_or_wake_command and should_call_llm:
            # 是否有过发送操作 and 是否是被 @ 或者通过唤醒前缀
            if (effective_result and not event.is_stopped()) or not effective_result:
                async for _ in self.agent_sub_stage.process(event):
                    yield
