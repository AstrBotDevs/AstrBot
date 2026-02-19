"""会话ID命令"""

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core import t


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
        ret = t(
            "builtin-stars-sid-base-info",
            sid=sid,
            user_id=user_id,
            umo_platform=umo_platform,
            umo_msg_type=umo_msg_type,
            umo_session_id=umo_session_id,
        )

        if (
            self.context.get_config()["platform_settings"]["unique_session"]
            and event.get_group_id()
        ):
            ret += t(
                "builtin-stars-sid-unique-session-group-tip",
                group_id=event.get_group_id(),
            )

        event.set_result(MessageEventResult().message(ret).use_t2i(False))
