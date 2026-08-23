from astrbot.api import star
from astrbot.api.event import AstrMessageEvent

from .reply import reply_i18n


class AdminCommands:
    def __init__(self, context: star.PluginContext) -> None:
        self.context = context

    async def list_admins(self, event: AstrMessageEvent) -> None:
        """List current authorization bindings without exposing credentials."""
        bindings = await self.context.authz.list_bindings(event)
        if not bindings:
            entries = await self.context.i18n.t(event, "admin.list.none")
        else:
            lines = [
                await self.context.i18n.t(
                    event,
                    "admin.list.item",
                    subject_id=binding.subject_id,
                    role=binding.role,
                    scope_type=binding.scope_type,
                )
                for binding in bindings
            ]
            entries = "\n".join(lines)
        await reply_i18n(self.context, event, "admin.list.header", entries=entries)

    async def grant(self, event: AstrMessageEvent, admin_id: str) -> None:
        """Grant a session-scoped administrator binding."""
        try:
            await self.context.authz.grant_session_admin(event, str(admin_id))
        except PermissionError, ValueError:
            await reply_i18n(self.context, event, "admin.grant.denied")
            return
        await reply_i18n(self.context, event, "admin.grant.ok")

    async def revoke(self, event: AstrMessageEvent, admin_id: str) -> None:
        """Revoke a session-scoped administrator binding."""
        try:
            revoked = await self.context.authz.revoke_session_admin(
                event, str(admin_id)
            )
        except PermissionError, ValueError:
            await reply_i18n(self.context, event, "admin.revoke.denied")
            return
        await reply_i18n(
            self.context,
            event,
            "admin.revoke.ok" if revoked else "admin.revoke.none",
        )
