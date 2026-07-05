from collections.abc import AsyncGenerator

from astrbot.core import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_type import MessageType

from ..context import PipelineContext
from ..stage import Stage, register_stage


@register_stage
class WhitelistCheckStage(Stage):
    """检查是否在群聊/私聊白名单"""

    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> None | AsyncGenerator[None, None]:
        platform_settings = self.ctx.astrbot_config["platform_settings"]
        blacklist = [
            str(i).strip()
            for i in platform_settings.get("id_blacklist", [])
            if str(i).strip()
        ]
        event_group_id = str(event.get_group_id()).strip()
        if event.unified_msg_origin in blacklist or event_group_id in blacklist:
            logger.info(
                "Session %s is in the session blacklist; stopping event propagation.",
                event.unified_msg_origin,
            )
            event.stop_event()
            return

        enable_whitelist_check = platform_settings["enable_id_white_list"]
        if not enable_whitelist_check:
            # 白名单检查未启用
            return

        whitelist = [
            str(i).strip()
            for i in platform_settings["id_whitelist"]
            if str(i).strip() != ""
        ]
        if len(whitelist) == 0:
            # 白名单为空，不检查
            return

        if event.get_platform_name() == "webchat":
            # WebChat 豁免
            return

        # 检查是否在白名单
        if platform_settings["wl_ignore_admin_on_group"]:
            if (
                event.role == "admin"
                and event.get_message_type() == MessageType.GROUP_MESSAGE
            ):
                return
        if platform_settings["wl_ignore_admin_on_friend"]:
            if (
                event.role == "admin"
                and event.get_message_type() == MessageType.FRIEND_MESSAGE
            ):
                return
        if (
            event.unified_msg_origin not in whitelist
            and event_group_id not in whitelist
        ):
            if platform_settings["id_whitelist_log"]:
                logger.info(
                    f"会话 ID {event.unified_msg_origin} 不在会话白名单中，已终止事件传播。请在配置文件中添加该会话 ID 到白名单。",
                )
            event.stop_event()
