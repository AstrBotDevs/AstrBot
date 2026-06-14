from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse

from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import TraceSettingsRequest
from astrbot.dashboard.services.log_service import LogService, LogServiceError

from .auth import AuthContext, require_dashboard_user, require_scope

router = APIRouter(tags=["Logs"])
legacy_router = APIRouter(
    prefix="/api",
    tags=["Dashboard Logs"],
    include_in_schema=False,
)


async def require_system_scope(request: Request) -> AuthContext:
    return await require_scope(request, "system")


def get_service(request: Request) -> LogService:
    return request.app.state.services.logs


def _raise_log_error(exc: LogServiceError) -> None:
    raise ApiError(str(exc)) from exc


def _log_stream_response(last_event_id: str | None, service: LogService):
    return StreamingResponse(
        service.stream_log_events(last_event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Transfer-Encoding": "chunked",
        },
    )


def _get_log_history(service: LogService):
    try:
        return ok(service.get_log_history())
    except LogServiceError as exc:
        _raise_log_error(exc)


def _get_trace_settings(service: LogService):
    try:
        return ok(service.get_trace_settings())
    except LogServiceError as exc:
        _raise_log_error(exc)


def _update_trace_settings(payload: TraceSettingsRequest, service: LogService):
    try:
        message = service.update_trace_settings(payload.model_dump(exclude_none=True))
        return ok(message=message)
    except LogServiceError as exc:
        _raise_log_error(exc)


@router.get("/logs/history")
async def get_log_history(
    _auth: AuthContext = Depends(require_system_scope),
    service: LogService = Depends(get_service),
):
    return _get_log_history(service)


@router.get("/logs/live")
async def live_logs(
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    _auth: AuthContext = Depends(require_system_scope),
    service: LogService = Depends(get_service),
):
    return _log_stream_response(last_event_id, service)


@router.get("/trace/settings")
async def get_trace_settings(
    _auth: AuthContext = Depends(require_system_scope),
    service: LogService = Depends(get_service),
):
    return _get_trace_settings(service)


@router.put("/trace/settings")
async def update_trace_settings(
    payload: TraceSettingsRequest,
    _auth: AuthContext = Depends(require_system_scope),
    service: LogService = Depends(get_service),
):
    return _update_trace_settings(payload, service)


@legacy_router.get("/log-history")
async def get_dashboard_log_history(
    _username: str = Depends(require_dashboard_user),
    service: LogService = Depends(get_service),
):
    return _get_log_history(service)


@legacy_router.get("/live-log")
async def get_dashboard_live_logs(
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    _username: str = Depends(require_dashboard_user),
    service: LogService = Depends(get_service),
):
    return _log_stream_response(last_event_id, service)


@legacy_router.get("/trace/settings")
async def get_dashboard_trace_settings(
    _username: str = Depends(require_dashboard_user),
    service: LogService = Depends(get_service),
):
    return _get_trace_settings(service)


@legacy_router.post("/trace/settings")
async def update_dashboard_trace_settings(
    payload: TraceSettingsRequest,
    _username: str = Depends(require_dashboard_user),
    service: LogService = Depends(get_service),
):
    return _update_trace_settings(payload, service)
