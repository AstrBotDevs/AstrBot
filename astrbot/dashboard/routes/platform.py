"""Unified webhook routes.

Provides a unified webhook callback entrypoint for multiple platforms.
"""

from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.dashboard.fastapi_compat import request
from astrbot.dashboard.services.platform_service import (
    PlatformService,
    PlatformServiceError,
)

from .route import Response, Route, RouteContext


class PlatformRoute(Route):
    """Unified webhook route."""

    def __init__(
        self,
        context: RouteContext,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.service = PlatformService(core_lifecycle)

        self._register_webhook_routes()

    def _register_webhook_routes(self) -> None:
        self.app.add_url_rule(
            "/api/platform/webhook/<webhook_uuid>",
            view_func=self.unified_webhook_callback,
            methods=["GET", "POST"],
        )

        self.app.add_url_rule(
            "/api/platform/stats",
            view_func=self.get_platform_stats,
            methods=["GET"],
        )

        self.app.add_url_rule(
            "/api/platform/registration/<platform_type>",
            view_func=self.handle_platform_registration,
            methods=["POST"],
        )

    @staticmethod
    def _ok(data=None):
        return Response().ok(data).__dict__

    @staticmethod
    def _error(exc: PlatformServiceError):
        return Response().error(str(exc)).__dict__, exc.status_code

    async def _run(self, operation):
        try:
            return self._ok(await operation())
        except PlatformServiceError as exc:
            return self._error(exc)

    async def _run_sync(self, operation):
        try:
            return self._ok(operation())
        except PlatformServiceError as exc:
            return self._error(exc)

    async def unified_webhook_callback(self, webhook_uuid: str):
        return await self._run(
            lambda: self.service.handle_webhook_callback(webhook_uuid, request)
        )

    async def get_platform_stats(self):
        return await self._run_sync(self.service.get_platform_stats)

    async def handle_platform_registration(self, platform_type: str):
        """Handle dashboard one-click platform registration actions."""
        payload = await request.get_json(silent=True) or {}
        return await self._run(
            lambda: self.service.handle_platform_registration(platform_type, payload)
        )
