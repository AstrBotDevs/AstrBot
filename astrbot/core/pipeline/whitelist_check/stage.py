from collections.abc import AsyncGenerator

from astrbot import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_type import MessageType

from ..context import PipelineContext
from ..stage import Stage


class WhitelistCheckStage(Stage):
    """检查是否在群聊/私聊白名单"""

    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.enable_whitelist_check = ctx.astrbot_config["platform_settings"][
            "enable_id_white_list"
        ]
        self.whitelist = ctx.astrbot_config["platform_settings"]["id_whitelist"]
        self.whitelist = [
            str(i).strip() for i in self.whitelist if str(i).strip() != ""
        ]
        self.wl_ignore_admin_on_group = ctx.astrbot_config["platform_settings"][
            "wl_ignore_admin_on_group"
        ]
        self.wl_ignore_admin_on_friend = ctx.astrbot_config["platform_settings"][
            "wl_ignore_admin_on_friend"
        ]
        self.wl_log = ctx.astrbot_config["platform_settings"]["id_whitelist_log"]

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> None | AsyncGenerator[None]:
        if not self.enable_whitelist_check:
            # 白名单检查未启用
            return

        if len(self.whitelist) == 0:
            # 白名单为空，不检查
            return

        if event.get_platform_name() == "webchat":
            # WebChat 豁免
            return

        # 检查是否在白名单
        if event.get_message_type() == MessageType.GROUP_MESSAGE:
            if self.wl_ignore_admin_on_group and await self._can_bypass(event):
                return
        elif event.get_message_type() == MessageType.FRIEND_MESSAGE:
            if self.wl_ignore_admin_on_friend and await self._can_bypass(event):
                return
        if (
            event.unified_msg_origin not in self.whitelist
            and str(event.get_group_id()).strip() not in self.whitelist
        ):
            if self.wl_log:
                logger.info(
                    f"会话 ID {event.unified_msg_origin} 不在会话白名单中，已终止事件传播。请在配置文件中添加该会话 ID 到白名单。",
                )
            event.stop_event()

    async def _can_bypass(self, event: AstrMessageEvent) -> bool:
        if (
            self.ctx.authorization is None
            or event.subject is None
            or event.resource is None
            or event.auth_context is None
        ):
            return False
        return (
            await self.ctx.authorization.authorize(
                event.subject,
                "provider.manage",
                event.resource,
                event.auth_context,
            )
        ).allowed
