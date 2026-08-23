from astrbot.api import star
from astrbot.api.event import AstrMessageEvent

from .reply import reply_i18n


class ChatCommands:
    def __init__(self, context: star.PluginContext) -> None:
        self.context = context

    async def status(self, event: AstrMessageEvent) -> None:
        """Show the LLM chat state for the current session."""
        umo = event.unified_msg_origin
        settings = await self.context.preferences.session_get(
            umo,
            "session_service_config",
            {},
        )
        enabled = settings.get("llm_enabled", True)
        await reply_i18n(
            self.context,
            event,
            "chat.status.enabled" if enabled else "chat.status.disabled",
        )

    async def set_enabled(
        self,
        event: AstrMessageEvent,
        enabled: bool,
    ) -> None:
        """Set the LLM chat state for the current session."""
        umo = event.unified_msg_origin
        settings = await self.context.preferences.session_get(
            umo,
            "session_service_config",
            {},
        )
        settings = dict(settings or {})
        settings["llm_enabled"] = enabled
        await self.context.preferences.session_put(
            umo,
            "session_service_config",
            settings,
        )
        await reply_i18n(
            self.context,
            event,
            "chat.set.enabled" if enabled else "chat.set.disabled",
        )
