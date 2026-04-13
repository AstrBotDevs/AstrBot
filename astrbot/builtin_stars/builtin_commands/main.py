from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, filter

from .commands import (
    AdminCommands,
    ConversationCommands,
    HelpCommand,
    SetUnsetCommands,
    SIDCommand,
)


class Main(star.Star):
    def __init__(self, context: star.Context) -> None:
        self.context = context

        self.admin_c = AdminCommands(self.context)
        self.conversation_c = ConversationCommands(self.context)
        self.help_c = HelpCommand(self.context)
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

    @filter.command("reset")
    async def reset(self, message: AstrMessageEvent) -> None:
        """Reset conversation history"""
        await self.conversation_c.reset(message)

    @filter.command("stop")
    async def stop(self, message: AstrMessageEvent) -> None:
        """Stop agent execution"""
        await self.conversation_c.stop(message)

    @filter.command("new")
    async def new_conv(self, message: AstrMessageEvent) -> None:
        """Create new conversation"""
        await self.conversation_c.new_conv(message)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("dashboard_update")
    async def update_dashboard(self, event: AstrMessageEvent) -> None:
        """Update AstrBot WebUI"""
        await self.admin_c.update_dashboard(event)

    @filter.command("set")
    async def set_variable(self, event: AstrMessageEvent, key: str, value: str) -> None:
        """Set session variable"""
        await self.setunset_c.set_variable(event, key, value)

    @filter.command("unset")
    async def unset_variable(self, event: AstrMessageEvent, key: str) -> None:
        """Unset session variable"""
        await self.setunset_c.unset_variable(event, key)
