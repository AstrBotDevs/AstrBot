from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageChain, MessageEventResult
from astrbot.core.config.default import VERSION
from astrbot.core.utils.io import download_dashboard


class AdminCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def op(self, event: AstrMessageEvent, admin_id: str = "") -> None:
        """授权管理员。op <admin_id>"""
        umo = event.unified_msg_origin
        if not admin_id:
            event.set_result(
                MessageEventResult().message(
                    "Usage: /op <id> to authorize admin; /deop <id> to deauthorize admin. Get the ID via /sid.",
                ),
            )
            return
        cfg = self.context.get_config(umo=umo)
        cfg["admins_id"].append(str(admin_id))
        cfg.save_config()
        event.set_result(MessageEventResult().message("✅ Authorized successfully."))

    async def deop(self, event: AstrMessageEvent, admin_id: str = "") -> None:
        """取消授权管理员。deop <admin_id>"""
        umo = event.unified_msg_origin
        cfg = self.context.get_config(umo=umo)
        if not admin_id:
            event.set_result(
                MessageEventResult().message(
                    "Usage: /deop <id> to deauthorize admin. Get the ID via /sid.",
                ),
            )
            return
        try:
            cfg["admins_id"].remove(str(admin_id))
            cfg.save_config()
            event.set_result(
                MessageEventResult().message("✅ Deauthorized successfully.")
            )
        except ValueError:
            event.set_result(
                MessageEventResult().message("⚠️ ID not found in admin list."),
            )

    async def update_dashboard(self, event: AstrMessageEvent) -> None:
        """更新管理面板"""
        await event.send(MessageChain().message("⏳ Updating dashboard..."))
        await download_dashboard(version=f"v{VERSION}", latest=False)
        await event.send(MessageChain().message("✅ Dashboard updated successfully."))
