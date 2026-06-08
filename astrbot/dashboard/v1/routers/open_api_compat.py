from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, WebSocket

from astrbot.dashboard.fastapi_compat import (
    CompatG,
    call_request_view,
    call_websocket_view,
)
from astrbot.dashboard.services.open_api_service import (
    OpenApiService,
    OpenApiServiceError,
)
from astrbot.dashboard.services.route_bridge_service import DashboardRouteBridgeService

from ..auth import AuthContext, require_scope
from ..responses import ApiError, ok

router = APIRouter(tags=["Open API Compatibility"])


async def require_im_scope(request: Request) -> AuthContext:
    return await require_scope(request, "im")


async def require_chat_scope(request: Request) -> AuthContext:
    return await require_scope(request, "chat")


async def require_config_scope(request: Request) -> AuthContext:
    return await require_scope(request, "config")


async def require_file_scope(request: Request) -> AuthContext:
    return await require_scope(request, "file")


def get_bridge(request: Request) -> DashboardRouteBridgeService:
    return request.app.state.services.route_bridge


def get_service(request: Request) -> OpenApiService:
    return request.app.state.services.open_api


async def _json_or_empty(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _compat_g(auth: AuthContext) -> CompatG:
    g_obj = CompatG()
    g_obj.username = auth.username
    return g_obj


async def _call_open_api_route(
    request: Request,
    auth: AuthContext,
    handler_name: str,
):
    route = getattr(request.app.state, "open_api_route", None)
    app_adapter = getattr(request.app.state, "dashboard_app_adapter", None)
    if route is None or app_adapter is None:
        raise ApiError("OpenAPI compatibility route is unavailable", status_code=503)
    return await call_request_view(
        request,
        app_adapter,
        getattr(route, handler_name),
        g_obj=_compat_g(auth),
    )


@router.post("/chat")
async def chat(
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    if auth.via == "api_key":
        return await _call_open_api_route(request, auth, "chat_send")
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/chat/send"
    )


@router.get("/chat/sessions")
async def chat_sessions(
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    if auth.via == "api_key":
        return await _call_open_api_route(request, auth, "get_chat_sessions")
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/chat/sessions"
    )


@router.get("/configs", include_in_schema=False)
async def get_chat_configs(
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
):
    return await _call_open_api_route(request, auth, "get_chat_configs")


@router.post("/file", include_in_schema=False)
async def upload_open_api_file(
    request: Request,
    auth: AuthContext = Depends(require_file_scope),
):
    return await _call_open_api_route(request, auth, "openapi_upload_file")


@router.get("/file", include_in_schema=False)
async def get_open_api_file(
    request: Request,
    auth: AuthContext = Depends(require_file_scope),
):
    return await _call_open_api_route(request, auth, "openapi_get_file")


@router.websocket("/chat/ws")
async def chat_ws(websocket: WebSocket) -> None:
    route = getattr(websocket.app.state, "open_api_route", None)
    app_adapter = getattr(websocket.app.state, "dashboard_app_adapter", None)
    if route is not None and app_adapter is not None:
        await call_websocket_view(websocket, app_adapter, route.chat_ws)
        return

    await websocket.accept()
    await websocket.close(1011, "OpenAPI chat websocket route is unavailable")


async def _forward_route_websocket(websocket: WebSocket, target_path: str) -> None:
    route_app = websocket.app.state.services.route_bridge.route_app
    receive = getattr(websocket, "_receive")
    send = getattr(websocket, "_send")
    scope = {
        **websocket.scope,
        "path": target_path,
        "raw_path": target_path.encode(),
    }
    await route_app(scope, receive, send)


@router.websocket("/live-chat/ws")
async def live_chat_ws(websocket: WebSocket) -> None:
    await _forward_route_websocket(websocket, "/api/live_chat/ws")


@router.websocket("/unified-chat/ws")
async def unified_chat_ws(websocket: WebSocket) -> None:
    await _forward_route_websocket(websocket, "/api/unified_chat/ws")


@router.post("/im/messages")
async def send_im_message(
    request: Request,
    _auth: AuthContext = Depends(require_im_scope),
    service: OpenApiService = Depends(get_service),
):
    body = await _json_or_empty(request)
    try:
        await service.send_message(body)
    except OpenApiServiceError as exc:
        raise ApiError(str(exc)) from exc

    return ok()


@router.post("/im/message", include_in_schema=False)
async def send_legacy_im_message(
    request: Request,
    auth: AuthContext = Depends(require_im_scope),
):
    return await _call_open_api_route(request, auth, "send_message")


@router.get("/im/bots")
async def list_im_bots(
    request: Request,
    _auth: AuthContext = Depends(require_im_scope),
    service: OpenApiService = Depends(get_service),
):
    return ok(service.get_bots())


async def _forward_platform_webhook(
    webhook_uuid: str,
    request: Request,
    bridge: DashboardRouteBridgeService,
):
    return await bridge.forward(
        request,
        None,
        method=request.method,
        target_path=f"/api/platform/webhook/{webhook_uuid}",
    )


@router.get("/webhooks/platforms/{webhook_uuid}")
async def verify_platform_webhook(
    webhook_uuid: str,
    request: Request,
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await _forward_platform_webhook(webhook_uuid, request, bridge)


@router.post("/webhooks/platforms/{webhook_uuid}")
async def receive_platform_webhook(
    webhook_uuid: str,
    request: Request,
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await _forward_platform_webhook(webhook_uuid, request, bridge)
