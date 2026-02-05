"""结果处理器

处理工具执行结果。
"""

from typing import Any
import mcp.types

from astrbot.core.tool_execution.interfaces import IResultProcessor


class ResultProcessor(IResultProcessor):
    """结果处理器实现"""
    
    async def process(self, result: Any) -> mcp.types.CallToolResult:
        """处理执行结果"""
        if result is None:
            return None
        
        if isinstance(result, mcp.types.CallToolResult):
            return result
        
        # 转换为TextContent
        text_content = mcp.types.TextContent(
            type="text",
            text=str(result),
        )
        return mcp.types.CallToolResult(content=[text_content])
