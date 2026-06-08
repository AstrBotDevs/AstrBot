from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.dashboard.fastapi_compat import jsonify, request
from astrbot.dashboard.services.subagent_service import (
    SubAgentService,
    SubAgentServiceError,
)

from .route import Response, Route, RouteContext


class SubAgentRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.service = SubAgentService(core_lifecycle)
        # NOTE: dict cannot hold duplicate keys; use list form to register multiple
        # methods for the same path.
        self.routes = [
            ("/subagent/config", ("GET", self.get_config)),
            ("/subagent/config", ("POST", self.update_config)),
            ("/subagent/available-tools", ("GET", self.get_available_tools)),
        ]
        self.register_routes()

    @staticmethod
    def _response(data=None, message: str | None = None):
        return jsonify(Response().ok(data=data, message=message).__dict__)

    @staticmethod
    def _error(message: str):
        return jsonify(Response().error(message).__dict__)

    async def _run(self, operation, *, message: str | None = None):
        try:
            return self._response(await operation(), message)
        except SubAgentServiceError as exc:
            return self._error(str(exc))

    async def _run_sync(self, operation):
        try:
            return self._response(operation())
        except SubAgentServiceError as exc:
            return self._error(str(exc))

    async def _run_json(self, operation, *, message: str | None = None):
        data = await request.json
        return await self._run(lambda: operation(data), message=message)

    async def get_config(self):
        return await self._run_sync(self.service.get_config)

    async def update_config(self):
        return await self._run_json(self.service.update_config, message="保存成功")

    async def get_available_tools(self):
        return await self._run_sync(self.service.get_available_tools)
