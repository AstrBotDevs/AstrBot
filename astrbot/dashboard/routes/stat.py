from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.dashboard.fastapi_compat import request
from astrbot.dashboard.services.stat_service import StatService, StatServiceError

from .route import Response, Route, RouteContext


class StatRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        db_helper: BaseDatabase,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.routes = {
            "/stat/get": ("GET", self.get_stat),
            "/stat/provider-tokens": ("GET", self.get_provider_token_stats),
            "/stat/version": ("GET", self.get_version),
            "/stat/start-time": ("GET", self.get_start_time),
            "/stat/restart-core": ("POST", self.restart_core),
            "/stat/test-ghproxy-connection": ("POST", self.test_ghproxy_connection),
            "/stat/changelog": ("GET", self.get_changelog),
            "/stat/changelog/list": ("GET", self.list_changelog_versions),
            "/stat/first-notice": ("GET", self.get_first_notice),
            "/stat/storage": ("GET", self.get_storage_status),
            "/stat/storage/cleanup": ("POST", self.cleanup_storage),
        }
        self.service = StatService(db_helper, core_lifecycle, self.config)
        self.register_routes()

    @staticmethod
    def _ok(data=None):
        return Response().ok(data).__dict__

    @staticmethod
    def _error(message: str):
        return Response().error(message).__dict__

    async def _run(self, operation):
        try:
            return self._ok(await operation())
        except StatServiceError as exc:
            return self._error(str(exc))

    async def _run_sync(self, operation):
        try:
            return self._ok(operation())
        except StatServiceError as exc:
            return self._error(str(exc))

    async def _run_json(self, operation, *, silent: bool = False):
        payload = await request.get_json(silent=silent)
        return await self._run(lambda: operation(payload))

    async def restart_core(self):
        return await self._run(self.service.restart_core)

    async def get_version(self):
        return await self._run(self.service.get_version)

    async def get_start_time(self):
        return await self._run_sync(self.service.get_start_time)

    async def get_storage_status(self):
        return await self._run(self.service.get_storage_status)

    async def cleanup_storage(self):
        return await self._run_json(
            self.service.cleanup_storage_from_legacy_payload,
            silent=True,
        )

    async def get_stat(self):
        return await self._run(
            lambda: self.service.get_stat_from_legacy_query(
                request.args.get("offset_sec", 86400)
            )
        )

    async def get_provider_token_stats(self):
        return await self._run(
            lambda: self.service.get_provider_token_stats_from_legacy_query(
                request.args.get("days", 1)
            )
        )

    async def test_ghproxy_connection(self):
        return await self._run_json(
            self.service.test_ghproxy_connection_from_legacy_payload
        )

    async def get_changelog(self):
        return await self._run_sync(
            lambda: self.service.get_changelog(request.args.get("version"))
        )

    async def list_changelog_versions(self):
        return await self._run_sync(self.service.list_changelog_versions)

    async def get_first_notice(self):
        return await self._run_sync(
            lambda: self.service.get_first_notice(request.args.get("locale"))
        )
