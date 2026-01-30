from __future__ import annotations

from astrbot.core import logger
from astrbot.core.pipeline.context import PipelineContext
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_type import MessageType
from astrbot.core.star.node_star import NodeResult


class AccessController:
    """Whitelist check (system-level mechanism)."""

    def __init__(self, ctx: PipelineContext):
        self._ctx = ctx
        self._initialized = False
        self.enable_whitelist_check: bool = False
        self.whitelist: list[str] = []
        self.wl_ignore_admin_on_group: bool = False
        self.wl_ignore_admin_on_friend: bool = False
        self.wl_log: bool = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        cfg = self._ctx.astrbot_config["platform_settings"]
        self.enable_whitelist_check = cfg["enable_id_white_list"]
        self.whitelist = [
            str(i).strip() for i in cfg["id_whitelist"] if str(i).strip() != ""
        ]
        self.wl_ignore_admin_on_group = cfg["wl_ignore_admin_on_group"]
        self.wl_ignore_admin_on_friend = cfg["wl_ignore_admin_on_friend"]
        self.wl_log = cfg["id_whitelist_log"]
        self._initialized = True

    async def apply(self, event: AstrMessageEvent) -> NodeResult:
        if not self.enable_whitelist_check:
            return NodeResult.CONTINUE

        if not self.whitelist:
            return NodeResult.CONTINUE

        if event.get_platform_name() == "webchat":
            return NodeResult.CONTINUE

        if self.wl_ignore_admin_on_group:
            if (
                event.role == "admin"
                and event.get_message_type() == MessageType.GROUP_MESSAGE
            ):
                return NodeResult.CONTINUE

        if self.wl_ignore_admin_on_friend:
            if (
                event.role == "admin"
                and event.get_message_type() == MessageType.FRIEND_MESSAGE
            ):
                return NodeResult.CONTINUE

        if (
            event.unified_msg_origin not in self.whitelist
            and str(event.get_group_id()).strip() not in self.whitelist
        ):
            if self.wl_log:
                logger.info(
                    f"会话 ID {event.unified_msg_origin} 不在会话白名单中，已终止事件传播。"
                )
            event.stop_event()
            return NodeResult.STOP

        return NodeResult.CONTINUE
