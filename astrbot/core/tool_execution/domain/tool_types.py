"""工具类型定义"""

from enum import Enum


class ToolType(Enum):
    """工具类型枚举"""
    LOCAL = "local"
    MCP = "mcp"
    HANDOFF = "handoff"


class ExecutionMode(Enum):
    """执行模式枚举"""
    SYNC = "sync"
    ASYNC = "async"
    BACKGROUND = "background"
