from __future__ import annotations

from typing import TYPE_CHECKING

from astrbot.dashboard.fastapi_compat import request
from astrbot.dashboard.services.update_service import (
    DEMO_MODE,
    UpdateService,
    UpdateServiceError,
    UpdateServiceResult,
    call_check_migration_needed_v4,
    call_do_migration_v4,
    call_download_dashboard,
    call_get_dashboard_version,
    call_pip_install,
)

from .route import Response, Route, RouteContext

if TYPE_CHECKING:
    from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
    from astrbot.core.updator import AstrBotUpdator

CLEAR_SITE_DATA_HEADERS = {"Clear-Site-Data": '"cache"'}


class UpdateRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        astrbot_updator: AstrBotUpdator,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.routes = {
            "/update/check": ("GET", self.check_update),
            "/update/progress": ("GET", self.get_update_progress),
            "/update/releases": ("GET", self.get_releases),
            "/update/do": ("POST", self.update_project),
            "/update/dashboard": ("POST", self.update_dashboard),
            "/update/pip-install": ("POST", self.install_pip_package),
            "/update/migration": ("POST", self.do_migration),
        }
        self.service = UpdateService(
            astrbot_updator,
            core_lifecycle,
            download_dashboard_func=call_download_dashboard,
            get_dashboard_version_func=call_get_dashboard_version,
            pip_install_func=call_pip_install,
            check_migration_needed_func=call_check_migration_needed_v4,
            do_migration_func=call_do_migration_v4,
            demo_mode=DEMO_MODE,
            clear_site_data_headers=CLEAR_SITE_DATA_HEADERS,
        )
        self.register_routes()

    @staticmethod
    def _service_response(result: UpdateServiceResult):
        if result.status == "success":
            payload = Response(
                status="success",
                message=result.message,
                data=result.data,
            ).__dict__
        else:
            payload = Response().ok(result.data, result.message).__dict__

        if result.headers:
            return payload, 200, result.headers
        return payload

    @staticmethod
    def _service_error(exc: UpdateServiceError):
        return Response().error(str(exc)).__dict__

    @staticmethod
    async def _json_body() -> dict:
        data = await request.get_json()
        return data if isinstance(data, dict) else {}

    async def _run(self, operation):
        try:
            result = operation() if callable(operation) else operation
            while hasattr(result, "__await__"):
                result = await result
            return self._service_response(result)
        except UpdateServiceError as exc:
            return self._service_error(exc)

    async def _run_json(self, operation):
        async def invoke():
            data = await self._json_body()
            return operation(data)

        return await self._run(invoke)

    async def get_update_progress(self):
        return await self._run(
            lambda: self.service.get_update_progress_from_legacy_query(
                request.args.get("id")
            )
        )

    async def do_migration(self):
        return await self._run_json(self.service.do_migration_v4)

    async def check_update(self):
        return await self._run(
            self.service.check_update_from_legacy_query(request.args.get("type"))
        )

    async def get_releases(self):
        return await self._run(self.service.get_releases())

    async def update_project(self):
        return await self._run_json(self.service.update_project)

    async def update_dashboard(self):
        return await self._run(self.service.update_dashboard())

    async def install_pip_package(self):
        return await self._run_json(self.service.install_pip_package)
