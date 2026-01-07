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
        # 仅保存配置引用，以便 process() 读取实时数据
        self._astrbot_config = ctx.astrbot_config

    def _get_whitelist(self) -> list[str]:
        """获取白名单列表"""
        raw_list = self._astrbot_config["platform_settings"]["id_whitelist"]
        return [str(i).strip() for i in raw_list if str(i).strip() != ""]

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> None | AsyncGenerator[None, None]:
        platform_settings = self._astrbot_config["platform_settings"]
        enable_whitelist_check = platform_settings["enable_id_white_list"]

        if not enable_whitelist_check:
            # 白名单检查未启用
            return

        whitelist = self._get_whitelist()
        if len(whitelist) == 0:
            # 白名单为空，不检查
            return

        if event.get_platform_name() == "webchat":
            # WebChat 豁免
            return

        # 读取配置项
        wl_ignore_admin_on_group = platform_settings["wl_ignore_admin_on_group"]
        wl_ignore_admin_on_friend = platform_settings["wl_ignore_admin_on_friend"]
        wl_log = platform_settings["id_whitelist_log"]

        # 检查是否在白名单
        if wl_ignore_admin_on_group:
            if (
                event.role == "admin"
                and event.get_message_type() == MessageType.GROUP_MESSAGE
            ):
                return
        if wl_ignore_admin_on_friend:
            if (
                event.role == "admin"
                and event.get_message_type() == MessageType.FRIEND_MESSAGE
            ):
                return
        if (
            event.unified_msg_origin not in whitelist
            and str(event.get_group_id()).strip() not in whitelist
        ):
            if wl_log:
                logger.info(
                    f"会话 ID {event.unified_msg_origin} 不在会话白名单中，已终止事件传播。请在配置文件中添加该会话 ID 到白名单。",
                )
            event.stop_event()
