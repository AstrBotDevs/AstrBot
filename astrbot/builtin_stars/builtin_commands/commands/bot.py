from astrbot.api import logger, safe_error, star
from astrbot.api.event import AstrMessageEvent

from .reply import reply_i18n, send_i18n

_SESSION_SERVICE_CONFIG = "session_service_config"


def _flag_enabled(settings: dict, key: str) -> bool:
    value = settings.get(key, True)
    return value if isinstance(value, bool) else True


class BotCommands:
    def __init__(self, context: star.PluginContext) -> None:
        self.context = context

    async def _service_config(self, umo: str) -> dict:
        settings = await self.context.preferences.session_get(
            umo,
            _SESSION_SERVICE_CONFIG,
            {},
        )
        return dict(settings or {})

    async def status(self, event: AstrMessageEvent) -> None:
        """Show bot version and session, LLM, and TTS switches."""
        settings = await self._service_config(event.unified_msg_origin)
        on_label = await self.context.i18n.t(event, "bot.status.on")
        off_label = await self.context.i18n.t(event, "bot.status.off")

        def label(key: str) -> str:
            return on_label if _flag_enabled(settings, key) else off_label

        await reply_i18n(
            self.context,
            event,
            "bot.status.body",
            version=self.context.runtime_info.version,
            session=label("session_enabled"),
            llm=label("llm_enabled"),
            tts=label("tts_enabled"),
        )

    async def set_enabled(self, event: AstrMessageEvent, enabled: bool) -> None:
        """Enable or disable the current session."""
        umo = event.unified_msg_origin
        settings = await self._service_config(umo)
        settings["session_enabled"] = enabled
        await self.context.preferences.session_put(
            umo,
            _SESSION_SERVICE_CONFIG,
            settings,
        )
        await reply_i18n(
            self.context,
            event,
            "bot.set.enabled" if enabled else "bot.set.disabled",
        )

    async def leave(self, event: AstrMessageEvent, *, confirm: bool = False) -> None:
        """Leave the current group after an explicit confirmation."""
        group_id = event.get_group_id()
        if not group_id:
            await reply_i18n(self.context, event, "bot.leave.private")
            return
        if not event.supports_platform_action("leave_group"):
            await reply_i18n(self.context, event, "bot.leave.unsupported")
            return
        if not confirm:
            await reply_i18n(self.context, event, "bot.leave.confirm")
            return

        await send_i18n(self.context, event, "bot.leave.ok")
        try:
            await self.context.platform_actions.invoke_for_event(
                event,
                "leave_group",
                group_id=group_id,
            )
        except Exception as exc:
            logger.warning("Failed to leave group: %s", safe_error("", exc))
            await send_i18n(self.context, event, "bot.leave.failed")
        event.clear_result()
        event.stop_event()
