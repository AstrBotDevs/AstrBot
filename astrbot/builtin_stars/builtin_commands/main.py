from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, filter

from .commands import (
    AdminCommands,
    ConversationCommands,
    HelpCommand,
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
        self.provider_c = ProviderCommands(self.context)
        self.setunset_c = SetUnsetCommands(self.context)
        self.sid_c = SIDCommand(self.context)

    @filter.command("help")
    async def help(self, event: AstrMessageEvent) -> None:
        """查看帮助信息"""
        await self.help_c.help(event)

    @filter.command("sid")
    async def sid(self, event: AstrMessageEvent) -> None:
        """获取会话 ID 及其他相关信息"""
        await self.sid_c.sid(event)

    @filter.command("reset")
    async def reset(self, message: AstrMessageEvent) -> None:
        """重置对话历史"""
        await self.conversation_c.reset(message)

    @filter.command("stop")
    async def stop(self, message: AstrMessageEvent) -> None:
        """停止 Agent 执行"""
        await self.conversation_c.stop(message)

    @filter.command("new")
    async def new_conv(self, message: AstrMessageEvent) -> None:
        """创建新对话"""
        await self.conversation_c.new_conv(message)

    @filter.command("stats")
    async def stats(self, message: AstrMessageEvent) -> None:
        """显示当前会话的 Token 用量统计"""
        await self.conversation_c.stats(message)

    @filter.command("context")
    async def context(self, message: AstrMessageEvent) -> None:
        """显示当前上下文窗口的 Token 占用"""
        await self.conversation_c.cmd_context(message)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("provider")
    async def provider(
        self,
        event: AstrMessageEvent,
        idx: str | int | None = None,
        idx2: int | None = None,
    ) -> None:
        """查看或切换 LLM Provider"""
        await self.provider_c.provider(event, idx, idx2)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("dashboard_update")
    async def update_dashboard(self, event: AstrMessageEvent) -> None:
        """更新 AstrBot WebUI"""
        await self.admin_c.update_dashboard(event)

    @filter.command("set")
    async def set_variable(self, event: AstrMessageEvent, key: str, value: str) -> None:
        """设置会话变量"""
        await self.setunset_c.set_variable(event, key, value)

    @filter.command("unset")
    async def unset_variable(self, event: AstrMessageEvent, key: str) -> None:
        """移除会话变量"""
        await self.setunset_c.unset_variable(event, key)
