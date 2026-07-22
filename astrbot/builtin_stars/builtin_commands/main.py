from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, filter
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

    @filter.command("reset")
    async def reset(self, message: AstrMessageEvent) -> None:
        """重置 LLM 会话"""
        await self.conversation_c.reset(message)

    @filter.command("compact")
    async def compact(self, message: AstrMessageEvent) -> None:
        """手动触发上下文的处置与压缩"""
        await self.conversation_c.compact(message)

    @filter.command("stop")
    async def stop(self, message: AstrMessageEvent) -> None:
        """停止当前会话中正在运行的 Agent"""
        await self.conversation_c.stop(message)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("model")
    async def model_ls(
        self,
        message: AstrMessageEvent,
        idx_or_name: int | str | None = None,
    ) -> None:
        """查看或者切换模型"""
        await self.provider_c.model_ls(message, idx_or_name)

    @filter.command("history")
    async def his(self, message: AstrMessageEvent, page: int = 1) -> None:
        """查看对话记录"""
        await self.conversation_c.his(message, page)

    @filter.command("ls")
    async def convs(self, message: AstrMessageEvent, page: int = 1) -> None:
        """查看对话列表"""
        await self.conversation_c.convs(message, page)

    @filter.command("new")
    async def new_conv(self, message: AstrMessageEvent) -> None:
        """创建新对话"""
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
