import astrbot.api.star as star
from astrbot.api.event import AstrMessageEvent, MessageEventResult, MessageChain
from astrbot.core.utils.io import download_dashboard
from astrbot.core.config.default import VERSION


class AdminCommands:
    def __init__(self, context: star.Context):
        self.context = context

    async def op(self, event: AstrMessageEvent, admin_id: str = ""):
        """授权管理员。op <admin_id>"""
        if not admin_id:
            event.set_result(
                MessageEventResult().message(
                    "使用方法: /op <id> 授权管理员；/deop <id> 取消管理员。可通过 /sid 获取 ID。"
                )
            )
            return
        self.context.get_config()["admins_id"].append(str(admin_id))
        self.context.get_config().save_config()
        event.set_result(MessageEventResult().message("授权成功。"))

    async def deop(self, event: AstrMessageEvent, admin_id: str = ""):
        """取消授权管理员。deop <admin_id>"""
        if not admin_id:
            event.set_result(
                MessageEventResult().message(
                    "使用方法: /deop <id> 取消管理员。可通过 /sid 获取 ID。"
                )
            )
            return
        try:
            self.context.get_config()["admins_id"].remove(str(admin_id))
            self.context.get_config().save_config()
            event.set_result(MessageEventResult().message("取消授权成功。"))
        except ValueError:
            event.set_result(
                MessageEventResult().message("此用户 ID 不在管理员名单内。")
            )

    async def wl(self, event: AstrMessageEvent, sid: str = ""):
        """添加白名单。wl <sid>"""
        if not sid:
            event.set_result(
                MessageEventResult().message(
                    "使用方法: /wl <id> 添加白名单；/dwl <id> 删除白名单。可通过 /sid 获取 ID。"
                )
            )
            return
        cfg = self.context.get_config(umo=event.unified_msg_origin)
        cfg["platform_settings"]["id_whitelist"].append(str(sid))
        cfg.save_config()
        event.set_result(MessageEventResult().message("添加白名单成功。"))

    async def dwl(self, event: AstrMessageEvent, sid: str = ""):
        """删除白名单。dwl <sid>"""
        if not sid:
            event.set_result(
                MessageEventResult().message(
                    "使用方法: /dwl <id> 删除白名单。可通过 /sid 获取 ID。"
                )
            )
            return
        try:
            cfg = self.context.get_config(umo=event.unified_msg_origin)
            cfg["platform_settings"]["id_whitelist"].remove(str(sid))
            cfg.save_config()
            event.set_result(MessageEventResult().message("删除白名单成功。"))
        except ValueError:
            event.set_result(MessageEventResult().message("此 SID 不在白名单内。"))

    async def update_dashboard(self, event: AstrMessageEvent):
        await event.send(MessageChain().message("正在尝试更新管理面板..."))
        await download_dashboard(version=f"v{VERSION}", latest=False)
        await event.send(MessageChain().message("管理面板更新完成。"))
