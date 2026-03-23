"""Tools registry for AstrBot internal runtime."""

from __future__ import annotations

from typing import Any

# Re-export from base
from astrbot._internal.tools.base import FunctionTool, ToolSet

__all__ = [
    "DEFAULT_MCP_CONFIG",
    "ENABLE_MCP_TIMEOUT_ENV",
    "FuncCall",
    "FunctionTool",
    "FunctionToolManager",
    "MCPAllServicesFailedError",
    "MCPInitError",
    "MCPInitSummary",
    "MCPInitTimeoutError",
    "MCPShutdownTimeoutError",
    "ToolSet",
]


# MCP config constants (re-exported from protocols)
try:
    from astrbot._internal.protocols.mcp import (
        DEFAULT_MCP_CONFIG,
        MCPAllServicesFailedError,
        MCPInitError,
        MCPInitSummary,
        MCPInitTimeoutError,
        MCPShutdownTimeoutError,
    )
except ImportError:
    DEFAULT_MCP_CONFIG: dict[str, Any] = {}
    MCPAllServicesFailedError: type[Exception] = Exception
    MCPInitError: type[Exception] = Exception
    MCPInitSummary: type[dict] = dict
    MCPInitTimeoutError: type[TimeoutError] = TimeoutError
    MCPShutdownTimeoutError: type[TimeoutError] = TimeoutError

ENABLE_MCP_TIMEOUT_ENV = "ASTRBOT_MCP_TIMEOUT_ENABLED"
MCP_INIT_TIMEOUT_ENV = "ASTRBOT_MCP_INIT_TIMEOUT"


class FunctionToolManager:
    """Central registry for all function tools."""

    def __init__(self) -> None:
        self.func_list: list[FunctionTool] = []

    def add(self, tool: FunctionTool) -> None:
        """Add a tool to the registry."""
        self.func_list.append(tool)

    def remove(self, name: str) -> bool:
        """Remove a tool by name. Returns True if found."""
        for i, f in enumerate(self.func_list):
            if f.name == name:
                self.func_list.pop(i)
                return True
        return False

    def get_func(self, name: str) -> FunctionTool | None:
        """Get a tool by name."""
        for f in self.func_list:
            if f.name == name:
                return f
        return None


class FuncCall(FunctionToolManager):
    """Alias for FunctionToolManager for backward compatibility."""

    def __init__(self) -> None:
        super().__init__()
