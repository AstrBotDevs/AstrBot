from astrbot.core.db import BaseDatabase
from astrbot.dashboard.fastapi_compat import g, request
from astrbot.dashboard.services.api_key_service import (
    ApiKeyService,
    ApiKeyServiceError,
)

from .route import Response, Route, RouteContext


class ApiKeyRoute(Route):
    def __init__(self, context: RouteContext, db: BaseDatabase) -> None:
        super().__init__(context)
        self.service = ApiKeyService(db)
        self.routes = {
            "/apikey/list": ("GET", self.list_api_keys),
            "/apikey/create": ("POST", self.create_api_key),
            "/apikey/revoke": ("POST", self.revoke_api_key),
            "/apikey/delete": ("POST", self.delete_api_key),
        }
        self.register_routes()

    @staticmethod
    def _ok(data=None):
        return Response().ok(data=data).__dict__

    @staticmethod
    def _error(message: str):
        return Response().error(message).__dict__

    async def _json_body(self):
        return await request.json or {}

    async def _run(self, operation):
        try:
            return self._ok(await operation())
        except ApiKeyServiceError as exc:
            return self._error(str(exc))

    async def _run_json(self, operation):
        payload = await self._json_body()
        return await self._run(lambda: operation(payload))

    async def list_api_keys(self):
        return await self._run(self.service.list_api_keys)

    async def create_api_key(self):
        return await self._run_json(
            lambda payload: self.service.create_api_key_from_legacy_payload(
                payload,
                created_by=g.get("username", "unknown"),
            )
        )

    async def revoke_api_key(self):
        return await self._run_json(self.service.revoke_api_key_from_legacy_payload)

    async def delete_api_key(self):
        return await self._run_json(self.service.delete_api_key_from_legacy_payload)
