"""会话ID命令"""

import astrbot.api.star as star
from astrbot.api.event import AstrMessageEvent, MessageEventResult


class SIDCommand:
    """会话ID命令类"""

    def __init__(self, context: star.Context):
        self.context = context

    async def sid(self, event: AstrMessageEvent):
        """获取消息来源信息"""
        sid = event.unified_msg_origin
        user_id = str(event.get_sender_id())
        umo_platform = event.session.platform_id
        umo_msg_type = event.session.message_type.value
        umo_session_id = event.session.session_id
        ret = (
            f"UMO: 「{sid}」 此值可用于设置白名单。\n"
            f"UID: 「{user_id}」 此值可用于设置管理员。\n"
            f"消息会话来源信息:\n"
            f"  机器人 ID: 「{umo_platform}」\n"
            f"  消息类型: 「{umo_msg_type}」\n"
            f"  会话 ID: 「{umo_session_id}」\n"
            f"消息来源可用于配置机器人的配置文件路由。"
        )

        if (
            self.context.get_config()["platform_settings"]["unique_session"]
            and event.get_group_id()
        ):
            ret += f"\n\n当前处于独立会话模式, 此群 ID: 「{event.get_group_id()}」, 也可将此 ID 加入白名单来放行整个群聊。"

        event.set_result(MessageEventResult().message(ret).use_t2i(False))
