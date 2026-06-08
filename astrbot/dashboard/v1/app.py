from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.dashboard.services.config_service import (
    BotConfigService,
    ConfigProfileService,
    ConfigRoutingService,
    ProviderConfigService,
)
from astrbot.dashboard.services.open_api_service import OpenApiService
from astrbot.dashboard.services.plugin_service import PluginService
from astrbot.dashboard.services.route_bridge_service import DashboardRouteBridgeService
from astrbot.dashboard.services.session_management_service import (
    SessionManagementService,
)

from .compat_aliases import router as compat_alias_router
from .responses import ApiError, error
from .routers import build_v1_router


def create_v1_asgi_app(
    *,
    core_lifecycle: AstrBotCoreLifecycle,
    db: BaseDatabase,
    jwt_secret: str,
) -> FastAPI:
    app = FastAPI(
        title="AstrBot OpenAPI",
        version="1.0.0",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
    )
    app.state.core_lifecycle = core_lifecycle
    app.state.db = db
    app.state.jwt_secret = jwt_secret
    app.state.services = SimpleNamespace(
        config_profiles=ConfigProfileService(core_lifecycle, db),
        config_routes=ConfigRoutingService(core_lifecycle),
        bots=BotConfigService(core_lifecycle),
        providers=ProviderConfigService(core_lifecycle),
        plugins=PluginService(core_lifecycle, core_lifecycle.plugin_manager),
        open_api=OpenApiService(db, core_lifecycle),
        sessions=SessionManagementService(core_lifecycle, db),
        route_bridge=None,
    )
    app.state.services.route_bridge = DashboardRouteBridgeService(app, jwt_secret)

    @app.exception_handler(ApiError)
    async def api_error_handler(_request: Request, exc: ApiError):
        return JSONResponse(
            error(exc.message, exc.data),
            status_code=exc.status_code,
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(_request: Request, exc: ValueError):
        return JSONResponse(error(str(exc)), status_code=400)

    @app.exception_handler(HTTPException)
    async def http_error_handler(_request: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return JSONResponse(error(detail), status_code=exc.status_code)

    app.include_router(compat_alias_router)
    app.include_router(build_v1_router())
    return app
