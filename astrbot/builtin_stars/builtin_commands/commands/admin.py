from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.core.config.default import VERSION
from astrbot.core.utils.io import download_dashboard


class AdminCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def update_dashboard(self, event: AstrMessageEvent) -> None:
        """更新管理面板"""
        await event.send(MessageChain().message("⏳ Updating dashboard..."))
        await download_dashboard(version=f"v{VERSION}", latest=False)
        await event.send(MessageChain().message("✅ Dashboard updated successfully."))
