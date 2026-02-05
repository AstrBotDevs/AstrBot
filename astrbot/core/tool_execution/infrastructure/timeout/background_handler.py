"""后台处理器

处理超时后转后台执行的逻辑。
"""

from typing import Any

import mcp.types

from astrbot.core.tool_execution.interfaces import ITimeoutHandler


class BackgroundHandler(ITimeoutHandler):
    """后台处理器实现"""

    def __init__(self, bg_manager=None):
        self._bg_manager = bg_manager

    @property
    def bg_manager(self):
        if self._bg_manager is None:
            from astrbot.core.background_tool import BackgroundToolManager

            self._bg_manager = BackgroundToolManager()
        return self._bg_manager

    async def handle_timeout(self, context: Any) -> mcp.types.CallToolResult:
        """处理超时，转后台执行"""
        task_id = await self.bg_manager.submit_task(
            tool_name=context["tool_name"],
            tool_args=context["tool_args"],
            session_id=context["session_id"],
            handler=context["handler"],
            wait=False,
            event=context.get("event"),
            event_queue=context.get("event_queue"),
        )

        return self._build_notification(context["tool_name"], task_id)

    def _build_notification(
        self, tool_name: str, task_id: str
    ) -> mcp.types.CallToolResult:
        """构建后台执行通知"""
        msg = (
            f"Tool '{tool_name}' switched to background.\n"
            f"Task ID: {task_id}\n"
            f"Use get_tool_output/wait_tool_result to check."
        )
        return mcp.types.CallToolResult(
            content=[mcp.types.TextContent(type="text", text=msg)]
        )
