import aiohttp

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.config.default import VERSION
from astrbot.core.dashboard_assets import get_dashboard_version
from astrbot.core.star import command_management

from ..i18n import MESSAGES, translate


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

    async def _build_reserved_command_lines(self, locale: str = "zh-CN") -> list[str]:
        """Build localized help from the active command configuration.

        Args:
            locale: System language for built-in command descriptions.

        Returns:
            Help lines preserving command renames and enabled states.
        """
        try:
            commands = await command_management.list_commands()
        except BaseException:
            return []

        lines: list[str] = []

        def walk(items: list[dict], indent: int = 0) -> None:
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

                description = item.get("description") or ""
                description_key = f"command.{item.get('handler_name')}"
                if (
                    item.get("module_path")
                    == "astrbot.builtin_stars.builtin_commands.main"
                    and description_key in MESSAGES["zh-CN"]
                ):
                    description = translate(description_key, locale)
                desc_text = f" - {description}" if description else ""
                indent_prefix = "  " * indent
                lines.append(f"{indent_prefix}/{effective}{desc_text}")

        walk(commands)
        return lines

    async def help(self, event: AstrMessageEvent) -> None:
        """查看帮助"""
        notice = ""
        try:
            notice = await self._query_astrbot_notice()
        except BaseException:
            pass

        dashboard_version = await get_dashboard_version()
        locale = self.context.locale(event.unified_msg_origin)
        command_lines = await self._build_reserved_command_lines(locale)
        commands_section = (
            "\n".join(command_lines)
            if command_lines
            else translate("no_commands", locale)
        )

        msg_parts = [
            f"AstrBot v{VERSION}(WebUI: {dashboard_version})",
            commands_section,
        ]
        if notice:
            msg_parts.append(notice)
        msg = "\n".join(msg_parts)

        event.set_result(MessageEventResult().message(msg).use_t2i(False))
