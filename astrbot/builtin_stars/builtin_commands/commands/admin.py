from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.core.updater import AstrBotUpdater


class AdminCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def update_dashboard(self, event: AstrMessageEvent) -> None:
        """更新管理面板"""
        await event.send(MessageChain().message("⏳ Updating dashboard..."))
        await AstrBotUpdater().ensure_dashboard()
        await event.send(MessageChain().message("✅ Dashboard updated successfully."))
