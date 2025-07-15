from ..stage import Stage, register_stage
from ..context import PipelineContext
from typing import AsyncGenerator, Union
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.session_llm_manager import SessionServiceManager
from astrbot.core import logger


@register_stage
class SessionStatusCheckStage(Stage):
    """检查会话是否整体启用"""

    async def initialize(self, ctx: PipelineContext) -> None:
        pass

    async def process(
        self, event: AstrMessageEvent
    ) -> Union[None, AsyncGenerator[None, None]]:
        # 检查会话是否整体启用
        if not SessionServiceManager.is_session_enabled(event.unified_msg_origin):
            logger.debug(f"会话 {event.unified_msg_origin} 已被关闭，已终止事件传播。")
            event.stop_event()
