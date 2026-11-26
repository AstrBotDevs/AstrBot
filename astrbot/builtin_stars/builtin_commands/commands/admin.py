from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.core.updater import AstrBotUpdater

from ..i18n import translate


class AdminCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def update_dashboard(self, event: AstrMessageEvent) -> None:
        """更新管理面板"""
        locale = await self.context.get_locale(event.unified_msg_origin)
        await event.send(
            MessageChain().message(translate("dashboard_updating", locale))
        )
        await AstrBotUpdater().ensure_dashboard()
        await event.send(MessageChain().message(translate("dashboard_updated", locale)))
