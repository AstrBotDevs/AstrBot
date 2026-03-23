"""MCP tool wrapper."""

from datetime import timedelta
from typing import Generic

from astrbot._internal.tools.base import FunctionTool
from astrbot.core.agent.run_context import ContextWrapper, TContext

from .client import MCPClient

try:
    import mcp
except (ModuleNotFoundError, ImportError):
    mcp = None  # type: ignore


class MCPTool(FunctionTool, Generic[TContext]):
    """A function tool that calls an MCP service."""

    def __init__(
        self, mcp_tool: mcp.Tool, mcp_client: MCPClient, mcp_server_name: str, **kwargs
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

    async def call(
        self, context: ContextWrapper[TContext], **kwargs
    ) -> mcp.types.CallToolResult:
        return await self.mcp_client.call_tool_with_reconnect(
            tool_name=self.mcp_tool.name,
            arguments=kwargs,
            read_timeout_seconds=timedelta(seconds=context.tool_call_timeout),
        )
