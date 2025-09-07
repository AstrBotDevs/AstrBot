"""
astrbot.api.tool
该模块包含了 AstrBot 有关大模型函数工具(包括MCP)的所有模块
"""

from astrbot.core.provider.func_tool_manager import FuncTool, MCPClient, FuncCall

__all__ = [
    "FuncTool",
    "MCPClient",
    "FuncCall",
]
