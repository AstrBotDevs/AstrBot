"""MCP module - Model Context Protocol client and tool implementations.

This module provides MCP client functionality and MCP tool wrappers.
"""

import asyncio
from dataclasses import dataclass

from .client import MCPClient
from .config import (
    DEFAULT_MCP_CONFIG,
    get_mcp_config_path,
    load_mcp_config,
    save_mcp_config,
)
from .tool import MCPTool


# Exceptions
class MCPInitError(Exception):
    """Base exception for MCP initialization failures."""


class MCPInitTimeoutError(asyncio.TimeoutError, MCPInitError):
    """Raised when MCP client initialization exceeds the configured timeout."""


class MCPAllServicesFailedError(MCPInitError):
    """Raised when all configured MCP services fail to initialize."""


class MCPShutdownTimeoutError(asyncio.TimeoutError):
    """Raised when MCP shutdown exceeds the configured timeout."""

    def __init__(self, names: list[str], timeout: float) -> None:
        self.names = names
        self.timeout = timeout
        message = f"MCP 服务关闭超时({timeout:g} 秒):{', '.join(names)}"
        super().__init__(message)


@dataclass
class MCPInitSummary:
    """Summary of MCP initialization results."""

    total: int
    success: int
    failed: list[str]


__all__ = [
    "DEFAULT_MCP_CONFIG",
    "MCPAllServicesFailedError",
    "MCPClient",
    "MCPInitError",
    "MCPInitSummary",
    "MCPInitTimeoutError",
    "MCPShutdownTimeoutError",
    "MCPTool",
    "get_mcp_config_path",
    "load_mcp_config",
    "save_mcp_config",
]
