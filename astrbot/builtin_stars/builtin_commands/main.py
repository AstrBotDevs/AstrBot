from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.core.session_overrides import update_overrides
from astrbot.core.star.filter.command import GreedyStr

from .commands import (
    AdminCommands,
    ConversationCommands,
    HelpCommand,
    NameCommand,
    ProviderCommands,
    SetUnsetCommands,
    SIDCommand,
)


class Main(star.Star):
    def __init__(self, context: star.Context) -> None:
        self.context = context

        self.admin_c = AdminCommands(self.context)
        self.conversation_c = ConversationCommands(self.context)
        self.help_c = HelpCommand(self.context)
        self.name_c = NameCommand(self.context)
        self.provider_c = ProviderCommands(self.context)
        self.setunset_c = SetUnsetCommands(self.context)
        self.sid_c = SIDCommand(self.context)

    @filter.command("help")
    async def help(self, event: AstrMessageEvent) -> None:
        """Show help message"""
        await self.help_c.help(event)

    @filter.command("sid")
    async def sid(self, event: AstrMessageEvent) -> None:
        """Get session ID and other related information"""
        await self.sid_c.sid(event)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("name")
    async def name(self, event: AstrMessageEvent, alias: GreedyStr) -> None:
        """Set display name for current UMO"""
        await self.name_c.name(event, alias)

    @filter.command("reset")
    @filter.permission_type(filter.PermissionType.SHARED_GROUP_ADMIN)
    async def reset(self, message: AstrMessageEvent) -> None:
        """Clear the context of the current conversation."""
        await self.conversation_c.reset(message)

    @filter.command("stop")
    async def stop(self, message: AstrMessageEvent) -> None:
        """Stop agent execution"""
        await self.conversation_c.stop(message)

    @filter.command("new")
    @filter.permission_type(filter.PermissionType.SHARED_GROUP_ADMIN)
    async def new_conv(self, message: AstrMessageEvent) -> None:
        """Create a new conversation."""
        await self.conversation_c.new_conv(message)

    @filter.command("stats")
    async def stats(self, message: AstrMessageEvent) -> None:
        """Show token usage statistics for the current conversation"""
        await self.conversation_c.stats(message)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("provider")
    async def provider(
        self,
        event: AstrMessageEvent,
        idx: str | int | None = None,
        idx2: int | None = None,
    ) -> None:
        """View or switch LLM Provider"""
        await self.provider_c.provider(event, idx, idx2)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("dashboard_update")
    async def update_dashboard(self, event: AstrMessageEvent) -> None:
        """Update AstrBot WebUI"""
        await self.admin_c.update_dashboard(event)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("persona")
    async def persona(self, event: AstrMessageEvent, name: GreedyStr = "") -> None:
        """Select the session persona or restore profile inheritance.

        Args:
            event: Command event identifying the target session.
            name: Persona name, or --inherit to follow the profile.
        """
        config = self.context.get_config(event.unified_msg_origin)
        path = (
            "agent.config.persona.persona_id"
            if config.get("agent", {}).get("runtime") == "astrbot"
            else "agent.config.persona_id"
        )
        name = name.strip()
        if not name:
            names = [item["name"] for item in self.context.persona_manager.personas_v3]
            event.set_result(
                event.plain_result(
                    "Usage: /persona <name> or /persona --inherit\n" + "\n".join(names)
                )
            )
            return
        if (
            name != "--inherit"
            and not self.context.persona_manager.get_persona_v3_by_id(name)
        ):
            event.set_result(event.plain_result("Persona not found."))
            return
        await update_overrides(
            event.unified_msg_origin, {path: None if name == "--inherit" else name}
        )
        event.set_result(
            event.plain_result(
                "Following profile persona."
                if name == "--inherit"
                else f"Session persona: {name}"
            )
        )

    @filter.command("set")
    async def set_variable(self, event: AstrMessageEvent, key: str, value: str) -> None:
        """Set session variable"""
        await self.setunset_c.set_variable(event, key, value)

    @filter.command("unset")
    async def unset_variable(self, event: AstrMessageEvent, key: str) -> None:
        """Unset session variable"""
        await self.setunset_c.unset_variable(event, key)
