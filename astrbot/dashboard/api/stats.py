from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import GhProxyTestRequest, StorageCleanupRequest
from astrbot.dashboard.services.stat_service import StatService, StatServiceError

from .auth import AuthContext, require_dashboard_user, require_scope

router = APIRouter(tags=["System Stats"])
legacy_router = APIRouter(
    prefix="/api/stat",
    tags=["Dashboard System Stats"],
    include_in_schema=False,
)


async def require_system_scope(request: Request) -> AuthContext:
    return await require_scope(request, "system")


def get_service(request: Request) -> StatService:
    return request.app.state.services.stats


def _raise_stat_error(exc: StatServiceError) -> None:
    raise ApiError(str(exc)) from exc


async def _run(operation):
    try:
        result = await run_maybe_async(operation)
        return ok(result)
    except StatServiceError as exc:
        _raise_stat_error(exc)


def _parse_int(value: object, default: int, name: str) -> int:
    if value is None:
        return default
    if not isinstance(value, int | float | str | bytes | bytearray):
        raise ApiError(f"{name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ApiError(f"{name} must be an integer") from exc


@router.get("/stats")
async def get_stats(
    offset_sec: int = Query(default=86400),
    _auth: AuthContext = Depends(require_system_scope),
    service: StatService = Depends(get_service),
):
    return await _run(service.get_stat(offset_sec))


@router.get("/stats/provider-tokens")
async def get_provider_token_stats(
    days: int = Query(default=1),
    _auth: AuthContext = Depends(require_system_scope),
    service: StatService = Depends(get_service),
):
    return await _run(service.get_provider_token_stats(days))


@router.get("/stats/version")
async def get_version(
    _auth: AuthContext = Depends(require_system_scope),
    service: StatService = Depends(get_service),
):
    return await _run(service.get_version())


@router.get("/stats/versions")
async def get_public_versions(
    request: Request,
    service: StatService = Depends(get_service),
):
    return ok(
        await service.get_public_versions(
            getattr(request.app.state, "dashboard_static_folder", None)
        )
    )


@router.get("/stats/first-notice")
async def get_first_notice(
    locale: str | None = None,
    _auth: AuthContext = Depends(require_system_scope),
    service: StatService = Depends(get_service),
):
    return await _run(lambda: service.get_first_notice(locale))


@router.post("/stats/ghproxy/test")
async def test_ghproxy_connection(
    payload: GhProxyTestRequest,
    _auth: AuthContext = Depends(require_system_scope),
    service: StatService = Depends(get_service),
):
    return await _run(service.test_ghproxy_connection(payload.proxy_url))


@router.get("/changelogs")
async def list_changelog_versions(
    _auth: AuthContext = Depends(require_system_scope),
    service: StatService = Depends(get_service),
):
    return await _run(service.list_changelog_versions)


@router.get("/changelogs/{version}")
async def get_changelog(
    version: str,
    _auth: AuthContext = Depends(require_system_scope),
    service: StatService = Depends(get_service),
):
    return await _run(lambda: service.get_changelog(version))


@router.get("/stats/start-time")
async def get_start_time(
    service: StatService = Depends(get_service),
):
    return await _run(service.get_start_time)


@router.get("/stats/storage")
async def get_storage_status(
    _auth: AuthContext = Depends(require_system_scope),
    service: StatService = Depends(get_service),
):
    return await _run(service.get_storage_status())


@router.post("/stats/storage/cleanup")
async def cleanup_storage(
    payload: StorageCleanupRequest,
    _auth: AuthContext = Depends(require_system_scope),
    service: StatService = Depends(get_service),
):
    return await _run(service.cleanup_storage(payload.target))


@router.post("/system/restart")
async def restart_system(
    _auth: AuthContext = Depends(require_system_scope),
    service: StatService = Depends(get_service),
):
    return await _run(service.restart_core())


@legacy_router.get("/get")
async def get_dashboard_stats(
    offset_sec: int | None = Query(default=86400),
    _username: str = Depends(require_dashboard_user),
    service: StatService = Depends(get_service),
):
    return await _run(service.get_stat(_parse_int(offset_sec, 86400, "offset_sec")))


@legacy_router.get("/provider-tokens")
async def get_dashboard_provider_token_stats(
    days: int | None = Query(default=1),
    _username: str = Depends(require_dashboard_user),
    service: StatService = Depends(get_service),
):
    return await _run(service.get_provider_token_stats(_parse_int(days, 1, "days")))


@legacy_router.get("/version")
async def get_dashboard_version(
    _username: str = Depends(require_dashboard_user),
    service: StatService = Depends(get_service),
):
    return await _run(service.get_version())


@legacy_router.get("/versions")
async def get_dashboard_public_versions(
    request: Request,
    service: StatService = Depends(get_service),
):
    return ok(
        await service.get_public_versions(
            getattr(request.app.state, "dashboard_static_folder", None)
        )
    )


@legacy_router.get("/start-time")
async def get_dashboard_start_time(
    service: StatService = Depends(get_service),
):
    return await _run(service.get_start_time)


@legacy_router.post("/restart-core")
async def restart_dashboard_core(
    _username: str = Depends(require_dashboard_user),
    service: StatService = Depends(get_service),
):
    return await _run(service.restart_core())


@legacy_router.post("/test-ghproxy-connection")
async def test_dashboard_ghproxy_connection(
    payload: GhProxyTestRequest,
    _username: str = Depends(require_dashboard_user),
    service: StatService = Depends(get_service),
):
    return await _run(service.test_ghproxy_connection(payload.proxy_url))


@legacy_router.get("/changelog")
async def get_dashboard_changelog(
    version: str | None = None,
    _username: str = Depends(require_dashboard_user),
    service: StatService = Depends(get_service),
):
    return await _run(lambda: service.get_changelog(version))


@legacy_router.get("/changelog/list")
async def list_dashboard_changelog_versions(
    _username: str = Depends(require_dashboard_user),
    service: StatService = Depends(get_service),
):
    return await _run(service.list_changelog_versions)


@legacy_router.get("/first-notice")
async def get_dashboard_first_notice(
    locale: str | None = None,
    _username: str = Depends(require_dashboard_user),
    service: StatService = Depends(get_service),
):
    return await _run(lambda: service.get_first_notice(locale))


@legacy_router.get("/storage")
async def get_dashboard_storage_status(
    _username: str = Depends(require_dashboard_user),
    service: StatService = Depends(get_service),
):
    return await _run(service.get_storage_status())


@legacy_router.post("/storage/cleanup")
async def cleanup_dashboard_storage(
    payload: StorageCleanupRequest | None = None,
    _username: str = Depends(require_dashboard_user),
    service: StatService = Depends(get_service),
):
    target = payload.target if payload is not None else "all"
    return await _run(service.cleanup_storage(target))
