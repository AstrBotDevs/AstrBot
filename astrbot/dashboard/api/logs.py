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


def _get_trace_history(service: LogService):
    try:
        return ok(service.get_trace_history())
    except LogServiceError as exc:
        _raise_log_error(exc)


async def _list_traces(
    service: LogService,
    page: int,
    page_size: int,
    umo: str | None,
    search: str | None,
    sender: str | None,
):
    try:
        return ok(
            await service.list_traces(
                page=page,
                page_size=page_size,
                umo=umo or None,
                search=search or None,
                sender=sender or None,
            )
        )
    except LogServiceError as exc:
        _raise_log_error(exc)


async def _get_trace_sources(service: LogService):
    try:
        return ok(await service.get_trace_sources())
    except LogServiceError as exc:
        _raise_log_error(exc)


async def _get_trace_detail(service: LogService, trace_id: str | None):
    try:
        return ok(await service.get_trace_detail(trace_id))
    except LogServiceError as exc:
        _raise_log_error(exc)


async def _clear_traces(service: LogService, before_ts: float | None):
    try:
        return ok(await service.clear_traces(before_ts))
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


@router.get("/trace/history")
async def get_trace_history(
    _auth: AuthContext = Depends(require_system_scope),
    service: LogService = Depends(get_service),
):
    return _get_trace_history(service)


@router.get("/trace/list")
async def list_traces(
    page: int = 1,
    page_size: int = 20,
    umo: str | None = None,
    search: str | None = None,
    sender: str | None = None,
    _auth: AuthContext = Depends(require_system_scope),
    service: LogService = Depends(get_service),
):
    return await _list_traces(service, page, page_size, umo, search, sender)


@router.get("/trace/sources")
async def get_trace_sources(
    _auth: AuthContext = Depends(require_system_scope),
    service: LogService = Depends(get_service),
):
    return await _get_trace_sources(service)


@router.get("/trace/detail")
async def get_trace_detail(
    trace_id: str | None = None,
    _auth: AuthContext = Depends(require_system_scope),
    service: LogService = Depends(get_service),
):
    return await _get_trace_detail(service, trace_id)


@router.delete("/trace/clear")
async def clear_traces(
    before_ts: float | None = None,
    _auth: AuthContext = Depends(require_system_scope),
    service: LogService = Depends(get_service),
):
    return await _clear_traces(service, before_ts)


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


@legacy_router.get("/trace/history")
async def get_dashboard_trace_history(
    _username: str = Depends(require_dashboard_user),
    service: LogService = Depends(get_service),
):
    return _get_trace_history(service)


@legacy_router.get("/trace/list")
async def list_dashboard_traces(
    page: int = 1,
    page_size: int = 20,
    umo: str | None = None,
    search: str | None = None,
    sender: str | None = None,
    _username: str = Depends(require_dashboard_user),
    service: LogService = Depends(get_service),
):
    return await _list_traces(service, page, page_size, umo, search, sender)


@legacy_router.get("/trace/sources")
async def get_dashboard_trace_sources(
    _username: str = Depends(require_dashboard_user),
    service: LogService = Depends(get_service),
):
    return await _get_trace_sources(service)


@legacy_router.get("/trace/detail")
async def get_dashboard_trace_detail(
    trace_id: str | None = None,
    _username: str = Depends(require_dashboard_user),
    service: LogService = Depends(get_service),
):
    return await _get_trace_detail(service, trace_id)


@legacy_router.delete("/trace/clear")
async def clear_dashboard_traces(
    before_ts: float | None = None,
    _username: str = Depends(require_dashboard_user),
    service: LogService = Depends(get_service),
):
    return await _clear_traces(service, before_ts)
