"""
MCP (Model Context Protocol) Public API for AstrBot.

Example:
    from astrbot.api.mcp import get_mcp_servers, register_mcp_server

    # List connected servers
    servers = get_mcp_servers()

    # Register stdio MCP server
    await register_mcp_server(
        name="weather",
        command="uv",
        args=["tool", "run", "weather-mcp"],
    )

    # Register SSE server
    await register_mcp_server(
        name="fileserver",
        url="http://localhost:8080/sse",
        transport="sse",
    )
"""

from __future__ import annotations

from typing import Any

from astrbot.core.agent.mcp_client import MCPClient, MCPTool
from astrbot.core.provider.func_tool_manager import FunctionToolManager

__all__ = [
    "MCPClient",
    "MCPTool",
    "get_mcp_servers",
    "register_mcp_server",
    "unregister_mcp_server",
]


def get_mcp_servers() -> dict[str, MCPClient]:
    """Get all connected MCP servers."""
    from astrbot.core.provider.register import llm_tools as func_tool_manager

    manager: FunctionToolManager = func_tool_manager
    return dict(manager.mcp_client_dict)


async def register_mcp_server(
    name: str,
    command: str | None = None,
    args: list[str] | None = None,
    url: str | None = None,
    transport: str | None = None,
    **kwargs: Any,
) -> None:
    """Register and connect to an MCP server.

    Args:
        name: Unique name for this server
        command: Command to run (for stdio transport)
        args: Command arguments
        url: URL (for SSE/Streamable HTTP transports)
        transport: "sse", "streamable_http", or None for stdio

    Example - Stdio:
        await register_mcp_server(name="weather", command="uv",
                                  args=["tool", "run", "weather-mcp"])
    """
    from astrbot.core.provider.register import llm_tools as func_tool_manager

    manager: FunctionToolManager = func_tool_manager

    config: dict[str, Any] = {}
    if command is not None:
        config["command"] = command
    if args is not None:
        config["args"] = args
    if url is not None:
        config["url"] = url
    if transport is not None:
        config["transport"] = transport
    config.update(kwargs)

    await manager.enable_mcp_server(name=name, config=config)


async def unregister_mcp_server(name: str) -> None:
    """Disconnect and remove an MCP server."""
    from astrbot.core.provider.register import llm_tools as func_tool_manager

    manager: FunctionToolManager = func_tool_manager
    await manager.disable_mcp_server(name=name)
