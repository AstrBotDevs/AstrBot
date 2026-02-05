"""结果处理器

处理工具执行结果。
"""

from typing import Any

import mcp.types

from astrbot import logger
from astrbot.core.tool_execution.interfaces import IResultProcessor


class ResultProcessor(IResultProcessor):
    """结果处理器实现"""

    def __init__(self, run_context: Any = None):
        self._run_context = run_context

    async def process(self, result: Any) -> mcp.types.CallToolResult | None:
        """处理执行结果

        Args:
            result: 工具执行返回值

        Returns:
            处理后的 CallToolResult，或 None 表示无需返回
        """
        if result is not None:
            return self._wrap_result(result)

        # result 为 None 时，检查是否需要直接发送消息给用户
        await self._send_direct_message()
        return None

    def _wrap_result(self, result: Any) -> mcp.types.CallToolResult:
        """包装结果为 CallToolResult"""
        if isinstance(result, mcp.types.CallToolResult):
            return result

        text_content = mcp.types.TextContent(
            type="text",
            text=str(result),
        )
        return mcp.types.CallToolResult(content=[text_content])

    async def _send_direct_message(self) -> None:
        """处理工具直接发送消息给用户的情况"""
        if self._run_context is None:
            return

        event = self._run_context.context.event
        if not event:
            return

        res = event.get_result()
        if not res or not res.chain:
            return

        try:
            from astrbot.core.message.message_event_result import MessageChain

            await event.send(
                MessageChain(
                    chain=res.chain,
                    type="tool_direct_result",
                )
            )
        except Exception as e:
            logger.error(f"Tool 直接发送消息失败: {e}", exc_info=True)
