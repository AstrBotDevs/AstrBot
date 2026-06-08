from astrbot.dashboard.fastapi_compat import request
from astrbot.dashboard.services.command_service import (
    CommandService,
    CommandServiceError,
)

from .route import Response, Route, RouteContext


class CommandRoute(Route):
    def __init__(self, context: RouteContext, core_lifecycle=None) -> None:
        super().__init__(context)
        self.service = CommandService(self.config, core_lifecycle)
        self.routes = {
            "/commands": ("GET", self.get_commands),
            "/commands/conflicts": ("GET", self.get_conflicts),
            "/commands/toggle": ("POST", self.toggle_command),
            "/commands/rename": ("POST", self.rename_command),
            "/commands/permission": ("POST", self.update_permission),
        }
        self.register_routes()

    @staticmethod
    def _ok(data=None):
        return Response().ok(data).__dict__

    @staticmethod
    def _error(message: str):
        return Response().error(message).__dict__

    @staticmethod
    async def _json_body() -> dict:
        data = await request.get_json()
        return data if isinstance(data, dict) else {}

    async def _run(self, operation):
        try:
            result = operation() if callable(operation) else operation
            while hasattr(result, "__await__"):
                result = await result
            return self._ok(result)
        except CommandServiceError as exc:
            return self._error(str(exc))

    async def _run_json(self, operation):
        async def invoke():
            data = await self._json_body()
            return operation(data)

        return await self._run(invoke)

    async def get_commands(self):
        return await self._run(
            self.service.list_commands_from_legacy_query(
                request.args.get("config_id", "")
            )
        )

    async def get_conflicts(self):
        return await self._run(self.service.list_conflicts())

    async def toggle_command(self):
        return await self._run_json(self.service.toggle_command_from_legacy_payload)

    async def rename_command(self):
        return await self._run_json(self.service.rename_command_from_legacy_payload)

    async def update_permission(self):
        return await self._run_json(self.service.update_permission_from_legacy_payload)
