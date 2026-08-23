from astrbot.api import star
from astrbot.api.event import AstrMessageEvent

from .reply import reply_i18n


class VariableCommands:
    def __init__(self, context: star.PluginContext) -> None:
        self.context = context

    async def set_variable(self, event: AstrMessageEvent, key: str, value: str) -> None:
        """Store a session variable."""
        uid = event.unified_msg_origin
        session_var = await self.context.preferences.session_get(
            uid, "session_variables", {}
        )
        session_var[key] = value
        await self.context.preferences.session_put(
            uid, "session_variables", session_var
        )
        await reply_i18n(
            self.context,
            event,
            "variable.set.ok",
            uid=uid,
            key=key,
        )

    async def unset_variable(self, event: AstrMessageEvent, key: str) -> None:
        """Remove a session variable."""
        uid = event.unified_msg_origin
        session_var = await self.context.preferences.session_get(
            uid, "session_variables", {}
        )
        if key not in session_var:
            await reply_i18n(self.context, event, "variable.unset.missing")
            return
        del session_var[key]
        await self.context.preferences.session_put(
            uid, "session_variables", session_var
        )
        await reply_i18n(
            self.context,
            event,
            "variable.unset.ok",
            uid=uid,
            key=key,
        )
