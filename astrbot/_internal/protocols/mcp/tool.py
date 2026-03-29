"""MCP tool wrapper."""

from datetime import timedelta
from typing import TYPE_CHECKING, Any

try:
    import mcp
except (ModuleNotFoundError, ImportError):
    mcp: Any = None

from astrbot._internal.tools.base import FunctionTool

if TYPE_CHECKING:
    from mcp.types import Tool as MCPTool_T
    from astrbot._internal.protocols.mcp.client import McpClient


class MCPTool(FunctionTool):
    """A function tool that calls an MCP service."""

    def __init__(
        self,
        mcp_tool: MCPTool_T,
        mcp_client: McpClient,
        mcp_server_name: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            name=mcp_tool.name,
            description=mcp_tool.description or "",
            parameters=mcp_tool.inputSchema,
        )
        self.mcp_tool = mcp_tool
        self.mcp_client = mcp_client
        self.mcp_server_name = mcp_server_name
        self.source = "mcp"

    async def call(self, **kwargs: Any) -> Any:
        """Call the MCP tool with the given arguments."""
        # Note: For actual usage, context.tool_call_timeout is needed
        # but for simplicity we use a default timeout here
        return await self.mcp_client.call_tool_with_reconnect(
            tool_name=self.mcp_tool.name,
            arguments=kwargs,
            read_timeout_seconds=timedelta(seconds=60),
        )
