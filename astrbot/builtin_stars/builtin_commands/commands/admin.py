from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult


class AdminCommands:
    def __init__(self, context: star.PluginContext) -> None:
        self.context = context

    async def list_admins(self, event: AstrMessageEvent) -> None:
        """List current authorization bindings without exposing credentials."""
        bindings = await self.context.authz.list_bindings(event)
        entries = [
            f"- {binding.subject_id}: {binding.role} ({binding.scope_type})"
            for binding in bindings
        ]
        message = "✅ Authorization bindings:\n" + ("\n".join(entries) or "- none")

        event.set_result(MessageEventResult().message(message).use_t2i(False))

    async def grant(self, event: AstrMessageEvent, admin_id: str) -> None:
        """Grant a session-scoped administrator binding."""
        try:
            await self.context.authz.grant_session_admin(event, str(admin_id))
        except PermissionError, ValueError:
            event.set_result(MessageEventResult().message("❌ Authorization denied."))
            return
        event.set_result(
            MessageEventResult().message("✅ Session administrator granted.")
        )

    async def revoke(self, event: AstrMessageEvent, admin_id: str) -> None:
        """Revoke a session-scoped administrator binding."""
        try:
            revoked = await self.context.authz.revoke_session_admin(
                event, str(admin_id)
            )
        except PermissionError, ValueError:
            event.set_result(MessageEventResult().message("❌ Authorization denied."))
            return
        event.set_result(
            MessageEventResult().message(
                "✅ Session administrator revoked."
                if revoked
                else "❌ Binding not found."
            )
        )
