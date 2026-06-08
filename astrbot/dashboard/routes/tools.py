from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.dashboard.fastapi_compat import request
from astrbot.dashboard.services.tools_service import ToolsService, ToolsServiceError

from .route import Response, Route, RouteContext


class ToolsRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.service = ToolsService(core_lifecycle)
        self.routes = {
            "/tools/mcp/servers": ("GET", self.get_mcp_servers),
            "/tools/mcp/add": ("POST", self.add_mcp_server),
            "/tools/mcp/update": ("POST", self.update_mcp_server),
            "/tools/mcp/delete": ("POST", self.delete_mcp_server),
            "/tools/mcp/test": ("POST", self.test_mcp_connection),
            "/tools/list": ("GET", self.get_tool_list),
            "/tools/toggle-tool": ("POST", self.toggle_tool),
            "/tools/mcp/sync-provider": ("POST", self.sync_provider),
        }
        self.register_routes()

    @staticmethod
    def _ok(data: dict | list | None = None, message: str | None = None) -> dict:
        return Response().ok(data, message).__dict__

    @staticmethod
    def _error(message: str) -> dict:
        return Response().error(message).__dict__

    @staticmethod
    async def _json_body() -> dict:
        data = await request.get_json()
        return data if isinstance(data, dict) else {}

    async def _run(self, operation, *, message: str | None = None) -> dict:
        try:
            result = operation() if callable(operation) else operation
            while hasattr(result, "__await__"):
                result = await result
            return self._ok(result, message)
        except ToolsServiceError as exc:
            return self._error(str(exc))

    async def _run_json(
        self,
        operation,
        *,
        message: str | None = None,
        result_as_message: bool = False,
    ) -> dict:
        async def invoke():
            data = await self._json_body()
            return operation(data)

        result = await self._run(invoke)
        if result_as_message and result.get("status") == "ok":
            return self._ok(None, result["data"])
        if message and result.get("status") == "ok":
            return self._ok(result.get("data"), message)
        return result

    async def get_mcp_servers(self):
        return await self._run(self.service.get_mcp_servers)

    async def add_mcp_server(self):
        return await self._run_json(self.service.add_mcp_server, result_as_message=True)

    async def update_mcp_server(self):
        return await self._run_json(
            self.service.update_mcp_server,
            result_as_message=True,
        )

    async def delete_mcp_server(self):
        return await self._run_json(
            self.service.delete_mcp_server,
            result_as_message=True,
        )

    async def test_mcp_connection(self):
        """Test MCP server connection."""
        return await self._run_json(
            self.service.test_mcp_connection,
            message="🎉 MCP server is available!",
        )

    async def get_tool_list(self):
        """Get all registered tools."""
        return await self._run(self.service.get_tool_list)

    async def toggle_tool(self):
        """Activate or deactivate a specified tool."""
        return await self._run_json(self.service.toggle_tool, result_as_message=True)

    async def sync_provider(self):
        """Sync MCP provider configuration."""
        return await self._run_json(self.service.sync_provider, result_as_message=True)
