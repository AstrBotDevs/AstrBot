from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult


class ToolCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def tool_ls(self, event: AstrMessageEvent) -> None:
        """查看函数工具列表"""
        event.set_result(
            MessageEventResult().message("tool 指令在 AstrBot v4.0.0 已经被移除。"),
        )

    async def tool_on(self, event: AstrMessageEvent, tool_name: str = "") -> None:
        """启用一个函数工具"""
        event.set_result(
            MessageEventResult().message("tool 指令在 AstrBot v4.0.0 已经被移除。"),
        )

    async def tool_off(self, event: AstrMessageEvent, tool_name: str = "") -> None:
        """停用一个函数工具"""
        event.set_result(
            MessageEventResult().message("tool 指令在 AstrBot v4.0.0 已经被移除。"),
        )

    async def tool_all_off(self, event: AstrMessageEvent) -> None:
        """停用所有函数工具"""
        event.set_result(
            MessageEventResult().message("tool 指令在 AstrBot v4.0.0 已经被移除。"),
        )
