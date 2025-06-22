from ..stage import Stage, register_stage
from ..context import PipelineContext
from typing import AsyncGenerator, Union
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core import logger


@register_stage
class BlacklistCheckStage(Stage):
    """检查是否在会话或用户黑名单中"""

    async def initialize(self, ctx: PipelineContext) -> None:
        ps = ctx.astrbot_config["platform_settings"]
        self.enable_blacklist = ps.get("enable_id_black_list", False)
        self.blacklist = [str(i).strip() for i in ps.get("id_blacklist", []) if str(i).strip() != ""]
        self.bl_log = ps.get("id_blacklist_log", True)

    async def process(
        self, event: AstrMessageEvent
    ) -> Union[None, AsyncGenerator[None, None]]:
        if not self.enable_blacklist:
            return
        sender = str(event.get_sender_id()).strip()
        group_id = str(event.get_group_id()).strip()
        if (
            event.unified_msg_origin in self.blacklist
            or sender in self.blacklist
            or group_id in self.blacklist
        ):
            if self.bl_log:
                logger.info(
                    f"会话 ID {event.unified_msg_origin} 在会话黑名单中，已终止事件传播。"
                )
            event.stop_event()
