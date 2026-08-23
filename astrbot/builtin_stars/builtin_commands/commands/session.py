from astrbot.api import star
from astrbot.api.event import AstrMessageEvent

from .reply import reply_i18n


class SessionCommands:
    def __init__(self, context: star.PluginContext) -> None:
        self.context = context

    async def info(self, event: AstrMessageEvent) -> None:
        """Show identifiers and metadata for the current session."""
        umo = event.unified_msg_origin
        group_id = event.get_group_id()
        unique_session = bool(
            self.context.config.get()["platform_settings"]["unique_session"]
        )
        group_note = ""
        if unique_session and group_id:
            group_note = await self.context.i18n.t(
                event,
                "session.info.group",
                group_id=group_id,
            )
        await reply_i18n(
            self.context,
            event,
            "session.info.body",
            umo=umo,
            user_id=str(event.get_sender_id()),
            platform_id=event.session.platform_id,
            message_type=event.session.message_type.value,
            session_id=event.session.session_id,
            group_note=group_note,
        )

    async def name(self, event: AstrMessageEvent, alias: str) -> None:
        """Show or set the display name for the current session."""
        umo = event.unified_msg_origin
        auto_name = self.context.sessions.auto_name(event)
        alias = self.context.sessions.normalize_name(alias)
        empty = await self.context.i18n.t(event, "session.name.empty")
        if not alias:
            saved_alias = await self.context.sessions.alias(umo)
            user_alias = self.context.sessions.normalize_name(
                saved_alias.user_alias if saved_alias else ""
            )
            await reply_i18n(
                self.context,
                event,
                "session.name.usage",
                umo=umo,
                auto_name=auto_name or empty,
                alias=user_alias or empty,
            )
            return

        await self.context.sessions.set_alias(
            umo=umo,
            creator_sender_id=str(event.get_sender_id() or ""),
            auto_name=auto_name,
            user_alias=alias,
        )
        await reply_i18n(
            self.context,
            event,
            "session.name.set",
            alias=alias,
            umo=umo,
        )
