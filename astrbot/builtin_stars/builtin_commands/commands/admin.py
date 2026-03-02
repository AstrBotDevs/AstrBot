from astrbot.core.lang import t
from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageChain, MessageEventResult
from astrbot.core.config.default import VERSION
from astrbot.core.utils.io import download_dashboard


class AdminCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def op(self, event: AstrMessageEvent, admin_id: str = "") -> None:
        """授权管理员。op <admin_id>"""
        if not admin_id:
            event.set_result(
                MessageEventResult().message(
                    t("msg-ad019976"),
                ),
            )
            return
        self.context.get_config()["admins_id"].append(str(admin_id))
        self.context.get_config().save_config()
        event.set_result(MessageEventResult().message(t("msg-1235330f")))

    async def deop(self, event: AstrMessageEvent, admin_id: str = "") -> None:
        """取消授权管理员。deop <admin_id>"""
        if not admin_id:
            event.set_result(
                MessageEventResult().message(
                    t("msg-e78847e0"),
                ),
            )
            return
        try:
            self.context.get_config()["admins_id"].remove(str(admin_id))
            self.context.get_config().save_config()
            event.set_result(MessageEventResult().message(t("msg-012152c1")))
        except ValueError:
            event.set_result(
                MessageEventResult().message(t("msg-5e076026")),
            )

    async def wl(self, event: AstrMessageEvent, sid: str = "") -> None:
        """添加白名单。wl <sid>"""
        if not sid:
            event.set_result(
                MessageEventResult().message(
                    t("msg-7f8eedde"),
                ),
            )
            return
        cfg = self.context.get_config(umo=event.unified_msg_origin)
        cfg["platform_settings"]["id_whitelist"].append(str(sid))
        cfg.save_config()
        event.set_result(MessageEventResult().message(t("msg-de1b0a87")))

    async def dwl(self, event: AstrMessageEvent, sid: str = "") -> None:
        """删除白名单。dwl <sid>"""
        if not sid:
            event.set_result(
                MessageEventResult().message(
                    t("msg-59d6fcbe"),
                ),
            )
            return
        try:
            cfg = self.context.get_config(umo=event.unified_msg_origin)
            cfg["platform_settings"]["id_whitelist"].remove(str(sid))
            cfg.save_config()
            event.set_result(MessageEventResult().message(t("msg-4638580f")))
        except ValueError:
            event.set_result(MessageEventResult().message(t("msg-278fb868")))

    async def update_dashboard(self, event: AstrMessageEvent) -> None:
        """更新管理面板"""
        await event.send(MessageChain().message(t("msg-1dee5007")))
        await download_dashboard(version=f"v{VERSION}", latest=False)
        await event.send(MessageChain().message(t("msg-76bea66c")))
