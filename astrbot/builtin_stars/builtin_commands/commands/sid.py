"""会话ID命令"""

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult


class SIDCommand:
    """会话ID命令类"""

    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def sid(self, event: AstrMessageEvent) -> None:
        """获取消息来源信息"""
        sid = event.unified_msg_origin
        user_id = str(event.get_sender_id())
        umo_platform = event.session.platform_id
        umo_msg_type = event.session.message_type.value
        umo_session_id = event.session.session_id
        ret = (
            f"UMO: 「{sid}」\n"
            f"UID: 「{user_id}」\n"
            "*UMO 可用于设置白名单和配置文件路由，UID 可用于设置管理员列表\n\n"
            f"您的会话信息:\n"
            f"Bot ID: 「{umo_platform}」\n"
            f"消息类型: 「{umo_msg_type}」\n"
            f"会话 ID: 「{umo_session_id}」\n\n"
        )

        if (
            self.context.get_config()["platform_settings"]["unique_session"]
            and event.get_group_id()
        ):
            ret += f"\n\n群组 ID: 「{event.get_group_id()}」。将此 ID 设为白名单可允许整个群组使用。"

        event.set_result(MessageEventResult().message(ret).use_t2i(False))
