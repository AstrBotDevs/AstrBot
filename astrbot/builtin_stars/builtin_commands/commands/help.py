import aiohttp

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.config.default import VERSION
from astrbot.core.star import command_management
from astrbot.core.utils.io import get_dashboard_version

TRANSLATIONS = {
    "en-US": {
        "no_commands": "No enabled built-in commands.",
        "version_format": "AstrBot v{version}(WebUI: {dashboard_version})",
        "commands": {
            "help": "Show help message",
            "sid": "Get session ID and other related information",
            "reset": "Reset conversation history",
            "stop": "Stop agent execution",
            "new": "Create new conversation",
            "stats": "Show token usage statistics for the current conversation",
            "provider": "View or switch LLM Provider",
            "dashboard_update": "Update AstrBot WebUI",
            "set": "Set session variable",
            "unset": "Unset session variable",
        },
    },
    "zh-CN": {
        "no_commands": "没有启用的内置指令。",
        "version_format": "AstrBot v{version}(WebUI: {dashboard_version})",
        "commands": {
            "help": "显示帮助信息",
            "sid": "获取会话ID和其他相关信息",
            "reset": "重置对话历史",
            "stop": "停止Agent执行",
            "new": "创建新对话",
            "stats": "显示当前对话的Token使用统计",
            "provider": "查看或切换LLM提供商",
            "dashboard_update": "更新AstrBot WebUI",
            "set": "设置会话变量",
            "unset": "取消设置会话变量",
        },
    },
    "zh-TW": {
        "no_commands": "沒有啟用的內建指令。",
        "version_format": "AstrBot v{version}(WebUI: {dashboard_version})",
        "commands": {
            "help": "顯示幫助信息",
            "sid": "獲取會話ID和其他相關信息",
            "reset": "重置對話歷史",
            "stop": "停止Agent執行",
            "new": "創建新對話",
            "stats": "顯示當前對話的Token使用統計",
            "provider": "查看或切換LLM提供商",
            "dashboard_update": "更新AstrBot WebUI",
            "set": "設置會話變量",
            "unset": "取消設置會話變量",
        },
    },
    "ru-RU": {
        "no_commands": "Нет включенных встроенных команд.",
        "version_format": "AstrBot v{version}(WebUI: {dashboard_version})",
        "commands": {
            "help": "Показать справку",
            "sid": "Получить ID сессии и другую информацию",
            "reset": "Сбросить историю диалога",
            "stop": "Остановить выполнение агента",
            "new": "Создать новый диалог",
            "stats": "Показать статистику использования токенов",
            "provider": "Просмотр или смена провайдера LLM",
            "dashboard_update": "Обновить AstrBot WebUI",
            "set": "Установить переменную сессии",
            "unset": "Сбросить переменную сессии",
        },
    },
}


class HelpCommand:
    def __init__(self, context: star.Context, config: dict | None = None) -> None:
        self.context = context
        self.config = config or {}
        self.language = self.config.get("help_language", "zh-CN")

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

    async def _build_reserved_command_lines(self) -> list[str]:
        try:
            commands = await command_management.list_commands()
        except BaseException:
            return []

        lines: list[str] = []

        def walk(items: list[dict], indent: int = 0) -> None:
            for item in items:
                if not item.get("reserved") or not item.get("enabled"):
                    continue
                if item.get("type") == "sub_command":
                    continue
                if item.get("parent_signature"):
                    continue

                effective = (
                    item.get("effective_command")
                    or item.get("original_command")
                    or item.get("handler_name")
                )
                if not effective:
                    continue

                description = item.get("description") or ""
                handler_name = item.get("handler_name", "")

                lang_translations = TRANSLATIONS.get(self.language, {})
                cmd_translations = lang_translations.get("commands", {})
                translated_desc = cmd_translations.get(handler_name, description)

                desc_text = f" - {translated_desc}" if translated_desc else ""
                indent_prefix = "  " * indent
                lines.append(f"{indent_prefix}/{effective}{desc_text}")

        walk(commands)
        return lines

    def _get_translation(self, key: str) -> str:
        lang_translations = TRANSLATIONS.get(self.language, TRANSLATIONS["zh-CN"])
        return lang_translations.get(key, key)

    async def help(self, event: AstrMessageEvent) -> None:
        notice = ""
        try:
            notice = await self._query_astrbot_notice()
        except BaseException:
            pass

        dashboard_version = await get_dashboard_version()
        command_lines = await self._build_reserved_command_lines()
        commands_section = (
            "\n".join(command_lines)
            if command_lines
            else self._get_translation("no_commands")
        )

        version_str = self._get_translation("version_format").format(
            version=VERSION, dashboard_version=dashboard_version
        )

        msg_parts = [
            version_str,
            commands_section,
        ]
        if notice:
            msg_parts.append(notice)
        msg = "\n".join(msg_parts)

        event.set_result(MessageEventResult().message(msg).use_t2i(False))
