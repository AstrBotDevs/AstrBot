from typing import Literal

from fastapi import APIRouter, Depends, Query, Request

from astrbot.core.auth.models import Resource
from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import GhProxyTestRequest, StorageCleanupRequest
from astrbot.dashboard.services.stat_service import StatService, StatServiceError

from .auth import AuthContext, require_resource_action, require_scope

router = APIRouter(tags=["System Stats"])


async def require_system_scope(request: Request) -> AuthContext:
    return await require_scope(request, "system")


async def require_system_restart_scope(request: Request) -> AuthContext:
    """Require the specific, reauthenticated capability to restart AstrBot."""

    auth = await require_scope(request, "system", authorize_action=False)
    await require_resource_action(
        request,
        auth,
        action="system.restart",
        resource=Resource.named("system", "restart"),
    )
    return auth


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
    locale: Literal["zh-CN", "en-US"] | None = None,
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


@router.get("/stats/t2i")
async def get_t2i_runtime_stats(
    _auth: AuthContext = Depends(require_system_scope),
    service: StatService = Depends(get_service),
):
    return await _run(service.get_t2i_runtime_stats)


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
    _auth: AuthContext = Depends(require_system_restart_scope),
    service: StatService = Depends(get_service),
):
    return await _run(service.restart_core())
