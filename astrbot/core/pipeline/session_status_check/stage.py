from collections.abc import AsyncGenerator

from astrbot.core import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.session_llm_manager import SessionServiceManager

from ..context import PipelineContext
from ..stage import Stage, register_stage


@register_stage
class SessionStatusCheckStage(Stage):
    """检查会话是否整体启用"""

    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.conv_mgr = ctx.plugin_manager.context.conversation_manager

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> None | AsyncGenerator[None, None]:
        # 检查会话是否整体启用
        if not await SessionServiceManager.is_session_enabled(event.unified_msg_origin):
            logger.debug(f"会话 {event.unified_msg_origin} 已被关闭，已终止事件传播。")

            # workaround for #2309
            conv_id = await self.conv_mgr.get_curr_conversation_id(
                event.unified_msg_origin,
            )
            if not conv_id:
                await self.conv_mgr.new_conversation(
                    event.unified_msg_origin,
                    platform_id=event.get_platform_id(),
                )

            event.stop_event()
