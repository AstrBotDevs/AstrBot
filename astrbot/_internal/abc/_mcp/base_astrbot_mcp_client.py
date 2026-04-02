"""
MCP (Model Context Protocol) client.

Transport: stdio | SSE | streamable_http
Messages:  JSON-RPC 2.0
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Literal, TypedDict

if TYPE_CHECKING:
    pass


class McpServerConfig(TypedDict, total=False):
    """MCP server configuration."""

    # Stdio transport
    command: str
    args: list[str]
    env: dict[str, str]
    cwd: str

    # HTTP transport
    url: str
    headers: dict[str, str]
    transport: Literal["sse", "streamable_http"]


class McpToolInfo(TypedDict):
    """MCP tool descriptor."""

    name: str
    description: str
    inputSchema: dict[str, Any]


class BaseAstrbotMcpClient(ABC):
    """
    MCP client: connects to MCP servers for external tools.

    Subclass must implement:
    - connect() -> None
    - connect_to_server(config, name) -> None
    - list_tools() -> list[McpToolInfo]
    - call_tool(name, args, timeout) -> CallToolResult
    - cleanup() -> None
    """

    session: Any  # mcp.ClientSession

    @property
    @abstractmethod
    def connected(self) -> bool: ...

    @abstractmethod
    async def connect(self) -> None:
        """Initialize client session."""
        ...

    @abstractmethod
    async def connect_to_server(
        self,
        config: McpServerConfig,
        name: str,
    ) -> None:
        """
        Connect to MCP server.

        Stdio: {"command": "python", "args": ["server.py"], "env": {...}}
        HTTP:  {"url": "https://...", "transport": "sse"}
        """
        ...

    @abstractmethod
    async def list_tools(self) -> list[McpToolInfo]:
        """Call tools/list and return tools."""
        ...

    @abstractmethod
    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        read_timeout_seconds: int = 60,
    ) -> Any:
        """Call tools/call with reconnection support."""
        ...

    @abstractmethod
    async def cleanup(self) -> None:
        """Close all server connections."""
        ...
