"""会话ID命令"""

import astrbot.api.star as star
from astrbot.api.event import AstrMessageEvent, MessageEventResult


class SIDCommand:
    """会话ID命令类"""

    def __init__(self, context: star.Context):
        self.context = context

    async def sid(self, event: AstrMessageEvent):
        """获取会话 ID 和 管理员 ID"""
        sid = event.unified_msg_origin
        user_id = str(event.get_sender_id())
        ret = f"""SID: {sid} 此 ID 可用于设置会话白名单。
/wl <SID> 添加白名单, /dwl <SID> 删除白名单。

UID: {user_id} 此 ID 可用于设置管理员。
/op <UID> 授权管理员, /deop <UID> 取消管理员。"""

        if (
            self.context.get_config()["platform_settings"]["unique_session"]
            and event.get_group_id()
        ):
            ret += f"\n\n当前处于独立会话模式, 此群 ID: {event.get_group_id()}, 也可将此 ID 加入白名单来放行整个群聊。"

        event.set_result(MessageEventResult().message(ret).use_t2i(False))
