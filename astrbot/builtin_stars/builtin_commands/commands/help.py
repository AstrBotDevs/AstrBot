import aiohttp

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.config.default import VERSION
from astrbot.core.dashboard_assets import get_dashboard_version
from astrbot.core.star import command_management

from .utils.i18n import command_desc


class HelpCommand:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def _query_astrbot_notice(self):
        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                async with session.get(
                    "https://astrbot.app/notice.json",
                    timeout=2,
                ) as resp:
                    return (await resp.json())["notice"]
        except BaseException:
            return ""

    async def _build_reserved_command_lines(self, lang: str, umo: str) -> list[str]:
        """
        使用实时指令配置生成内置指令清单，确保重命名/禁用后与实际生效状态保持一致。
        指令名显示实际生效名;描述优先取内置描述表(按当前语言),再回退原文。
        """
        try:
            commands = await command_management.list_commands()
        except BaseException:
            return []

        reserved: list[tuple[str, str]] = []  # (effective, 原始描述)

        def walk(items: list[dict]) -> None:
            for item in items:
                if not item.get("reserved") or not item.get("enabled"):
                    continue
                # 仅展示顶级指令或指令组
                if item.get("type") == "sub_command":
                    continue
                if item.get("parent_signature"):
                    continue

                effective = (
                    item.get("effective_command")
                    or item.get("original_command")
                    or item.get("handler_name")
                )
                if not effective or effective in [
                    "set",
                    "unset",
                    "help",
                    "dashboard_update",
                ]:
                    continue

                descriptions = item.get("descriptions") or {}
                description = descriptions.get(lang) or item.get("description") or ""
                reserved.append((effective, description))

        walk(commands)

        # 排序:/lang 固定排在最后;其余按字母序
        reserved.sort(key=lambda pair: (pair[0] == "lang", pair[0]))

        lines = []
        for effective, fallback_desc in reserved:
            desc = await command_desc(self.context, umo, effective) or fallback_desc
            desc_text = f" - {desc}" if desc else ""
            lines.append(f"/{effective}{desc_text}")
        return lines

    async def help(self, event: AstrMessageEvent) -> None:
        """查看帮助"""
        notice = ""
        try:
            notice = await self._query_astrbot_notice()
        except BaseException:
            pass

        dashboard_version = await get_dashboard_version()
        lang = await self.context.get_lang(event.unified_msg_origin)
        command_lines = await self._build_reserved_command_lines(
            lang, event.unified_msg_origin
        )
        commands_section = (
            "\n".join(command_lines)
            if command_lines
            else "No enabled built-in commands."
        )

        msg_parts = [
            f"AstrBot v{VERSION}(WebUI: {dashboard_version})",
            commands_section,
        ]
        if notice:
            msg_parts.append(notice)
        msg = "\n".join(msg_parts)

        event.set_result(MessageEventResult().message(msg).use_t2i(False))
