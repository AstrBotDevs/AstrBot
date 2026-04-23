from astrbot.api import sp, star
from astrbot.api.event import AstrMessageEvent, MessageEventResult

from ..i18n import t


class SetUnsetCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def set_variable(self, event: AstrMessageEvent, key: str, value: str) -> None:
        """设置会话变量"""
        uid = event.unified_msg_origin
        session_var = await sp.session_get(uid, "session_variables", {})
        session_var[key] = value
        await sp.session_put(uid, "session_variables", session_var)

        event.set_result(
            MessageEventResult().message(
                t(
                    self.context,
                    "setunset.set_success",
                    session_id=uid,
                    key=key,
                ),
            ),
        )

    async def unset_variable(self, event: AstrMessageEvent, key: str) -> None:
        """移除会话变量"""
        uid = event.unified_msg_origin
        session_var = await sp.session_get(uid, "session_variables", {})

        if key not in session_var:
            event.set_result(
                MessageEventResult().message(
                    t(self.context, "setunset.unset_not_found")
                ),
            )
        else:
            del session_var[key]
            await sp.session_put(uid, "session_variables", session_var)
            event.set_result(
                MessageEventResult().message(
                    t(
                        self.context,
                        "setunset.unset_success",
                        session_id=uid,
                        key=key,
                    ),
                ),
            )
