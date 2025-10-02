import astrbot.api.star as star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api import sp


class SetUnsetCommands:
    def __init__(self, context: star.Context):
        self.context = context

    async def set_variable(self, event: AstrMessageEvent, key: str, value: str):
        """设置会话变量"""
        uid = event.unified_msg_origin
        session_var = await sp.session_get(uid, "session_variables", {})
        session_var[key] = value
        await sp.session_put(uid, "session_variables", session_var)

        event.set_result(
            MessageEventResult().message(
                f"会话 {uid} 变量 {key} 存储成功。使用 /unset 移除。"
            )
        )

    async def unset_variable(self, event: AstrMessageEvent, key: str):
        """移除会话变量"""
        uid = event.unified_msg_origin
        session_var = await sp.session_get(uid, "session_variables", {})

        if key not in session_var:
            event.set_result(
                MessageEventResult().message("没有那个变量名。格式 /unset 变量名。")
            )
        else:
            del session_var[key]
            await sp.session_put(uid, "session_variables", session_var)
            event.set_result(
                MessageEventResult().message(f"会话 {uid} 变量 {key} 移除成功。")
            )
