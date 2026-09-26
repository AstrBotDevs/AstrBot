from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.core.updater import AstrBotUpdater

from .utils.i18n import t


class AdminCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def update_dashboard(self, event: AstrMessageEvent) -> None:
        """更新管理面板"""
        await event.send(
            MessageChain().message(
                await t(
                    self.context,
                    event.unified_msg_origin,
                    "dashboard.updating",
                )
            )
        )
        await AstrBotUpdater().ensure_dashboard()
        await event.send(
            MessageChain().message(
                await t(
                    self.context,
                    event.unified_msg_origin,
                    "dashboard.done",
                )
            )
        )
