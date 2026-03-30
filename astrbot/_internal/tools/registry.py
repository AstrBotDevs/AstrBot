"""Tools registry for AstrBot internal runtime."""

from __future__ import annotations

from typing import Any

# Re-export from base
from astrbot._internal.tools.base import FunctionTool, ToolSchema, ToolSet

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
        self._func_list: list[ToolSchema] = []

    @property
    def func_list(self) -> list[ToolSchema]:
        """Get the list of function tools."""
        return self._func_list

    @func_list.setter
    def func_list(self, value: list[ToolSchema]) -> None:
        """Set the list of function tools."""
        self._func_list = value

    def add(self, tool: ToolSchema) -> None:
        """Add a tool to the registry."""
        self._func_list.append(tool)

    def remove(self, name: str) -> bool:
        """Remove a tool by name. Returns True if found."""
        for i, f in enumerate(self._func_list):
            if f.name == name:
                self._func_list.pop(i)
                return True
        return False

    def get_func(self, name: str) -> ToolSchema | None:
        """Get a tool by name. Returns the last active tool if multiple match."""
        last_match: ToolSchema | None = None
        for f in reversed(self._func_list):
            if f.name == name:
                if getattr(f, "active", True):
                    return f
                if last_match is None:
                    last_match = f
        return last_match

    def get_full_tool_set(self) -> ToolSet:
        """Return a ToolSet with all active tools, deduplicated by name."""
        seen: dict[str, ToolSchema] = {}
        for tool in reversed(self._func_list):
            if tool.name not in seen and getattr(tool, "active", True):
                seen[tool.name] = tool
        return ToolSet("default", list(seen.values()))

    def register_internal_tools(self) -> None:
        """Register built-in computer tools (shell, python, browser, neo)."""
        # Import here to avoid circular imports
        from astrbot.core.computer.computer_tool_provider import get_all_tools

        for tool in get_all_tools():
            if self.get_func(tool.name) is None:
                self.add(tool)  # type: ignore[arg-type]

    # MCP-related stub methods for base class compatibility
    async def enable_mcp_server(
        self, name: str, config: dict[str, Any], init_timeout: int = 30
    ) -> None:
        """Enable an MCP server (stub)."""
        pass

    async def disable_mcp_server(
        self, name: str = "", timeout: int = 10, shutdown_timeout: int = 10
    ) -> None:
        """Disable an MCP server (stub)."""
        pass

    async def init_mcp_clients(self) -> None:
        """Initialize MCP clients (stub)."""
        pass

    async def test_mcp_server_connection(
        self, config: dict[str, Any]
    ) -> tuple[bool, str]:
        """Test MCP server connection (stub)."""
        return False, "Not implemented"

    async def sync_modelscope_mcp_servers(self) -> None:
        """Sync ModelScope MCP servers (stub)."""
        pass

    def load_mcp_config(self) -> dict[str, Any]:
        """Load MCP configuration (stub)."""
        return {"mcpServers": {}}

    def save_mcp_config(self, config: dict[str, Any]) -> bool:
        """Save MCP configuration (stub)."""
        return True

    def activate_llm_tool(self, name: str) -> bool:
        """Activate an LLM tool (stub)."""
        return True

    def deactivate_llm_tool(self, name: str) -> bool:
        """Deactivate an LLM tool (stub)."""
        return True

    @property
    def mcp_client_dict(self) -> dict[str, Any]:
        """Return dict of MCP clients (stub)."""
        return {}

    @property
    def mcp_server_runtime_view(self) -> dict[str, Any]:
        """Return runtime view of MCP servers (stub)."""
        return {}


class FuncCall(FunctionToolManager):
    """Alias for FunctionToolManager for backward compatibility."""

    def __init__(self) -> None:
        super().__init__()
        self._mcp_server_runtime_view: dict[str, Any] = {}
        self._mcp_client_dict: dict[str, Any] = {}

    @property
    def mcp_server_runtime_view(self) -> dict[str, Any]:
        """Return runtime view of MCP servers."""
        return self._mcp_server_runtime_view

    @property
    def mcp_client_dict(self) -> dict[str, Any]:
        """Return dict of MCP clients (for backward compatibility)."""
        return self._mcp_client_dict

    async def init_mcp_clients(self) -> None:
        """Initialize MCP clients (stub implementation)."""
        pass

    def add_func(
        self,
        name: str,
        func_args: list[dict[str, Any]],
        desc: str,
        handler: Any,
    ) -> None:
        """Add a function tool (deprecated, use add() instead)."""
        params: dict[str, Any] = {
            "type": "object",
            "properties": {},
        }
        for param in func_args:
            params["properties"][param["name"]] = {
                "type": param.get("type", "string"),
                "description": param.get("description", ""),
            }
        func = FunctionTool(
            name=name,
            parameters=params,
            description=desc,
            handler=handler,
        )
        self.add(func)

    def remove_func(self, name: str) -> None:
        """Remove a function tool by name (deprecated, use remove() instead)."""
        self.remove(name)

    def get_func(self, name: str) -> ToolSchema | None:
        """Get a function tool by name."""
        return super().get_func(name)

    def names(self) -> list[str]:
        """Get all tool names."""
        return [f.name for f in self.func_list]

    def remove_tool(self, name: str) -> None:
        """Remove a tool by its name (alias for remove)."""
        self.remove(name)

    def get_func_desc_openai_style(
        self, omit_empty_parameter_field: bool = False
    ) -> list[dict[str, Any]]:
        """Get tools in OpenAI style (deprecated, use get_full_tool_set().openai_schema())."""
        tool_set = self.get_full_tool_set()
        return tool_set.openai_schema(omit_empty_parameter_field)

    async def enable_mcp_server(
        self, name: str, config: dict[str, Any], init_timeout: int = 30
    ) -> None:
        """Enable an MCP server (stub implementation)."""
        pass

    async def disable_mcp_server(
        self, name: str = "", timeout: int = 10, shutdown_timeout: int = 10
    ) -> None:
        """Disable an MCP server (stub implementation)."""
        pass

    def load_mcp_config(self) -> dict[str, Any]:
        """Load MCP configuration (stub implementation)."""
        return {"mcpServers": {}}

    def save_mcp_config(self, config: dict[str, Any]) -> bool:
        """Save MCP configuration (stub implementation)."""
        return True

    def activate_llm_tool(self, name: str) -> bool:
        """Activate an LLM tool (stub implementation)."""
        return True

    def deactivate_llm_tool(self, name: str) -> bool:
        """Deactivate an LLM tool (stub implementation)."""
        return True

    async def test_mcp_server_connection(
        self, config: dict[str, Any]
    ) -> tuple[bool, str]:
        """Test MCP server connection (stub implementation)."""
        # Import the actual test function if available
        try:
            from astrbot._internal.protocols.mcp.client import (
                _quick_test_mcp_connection,
            )

            success, message = await _quick_test_mcp_connection(config)
            if not success:
                raise Exception(message)
            return success, message
        except Exception as e:
            raise Exception(f"MCP connection test failed: {e!s}") from e

    async def sync_modelscope_mcp_servers(self) -> None:
        """Sync ModelScope MCP servers (stub implementation)."""
        pass

    def get_full_tool_set(self) -> ToolSet:
        """Return a ToolSet with all active tools."""
        return ToolSet("default", [t for t in self.func_list if t.active])
