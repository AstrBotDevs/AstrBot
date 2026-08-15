from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from astrbot import logger
from astrbot.core.auth.models import AuthorizationValueError, Resource
from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.responses import ApiError, error, ok
from astrbot.dashboard.schemas import (
    BatchSessionProviderRequest,
    BatchSessionServiceRequest,
    SessionGroupRequest,
    SessionRuleRequest,
    UmoListRequest,
)
from astrbot.dashboard.services.session_management_service import (
    SessionManagementService,
    SessionManagementServiceError,
)

from .auth import AuthContext, require_resource_action, require_scope
from .error_handling import internal_error_response

router = APIRouter(tags=["Sessions"])


def get_service(request: Request) -> SessionManagementService:
    return request.app.state.services.sessions


async def require_data_scope(request: Request) -> AuthContext:
    return await require_scope(request, "data")


async def _payload_umos(
    service: SessionManagementService,
    payload: dict,
) -> list[str]:
    """Resolve direct or scope-selected UMO targets before a mutation."""

    direct_umo = payload.get("umo")
    if direct_umo:
        return service._validate_umo_list([direct_umo])
    umos = payload.get("umos")
    if umos:
        return service._validate_umo_list(umos)
    scope = payload.get("scope")
    if scope:
        return await service.get_umos_by_scope(scope, payload.get("group_id", ""))
    return []


async def _authorize_session_umos(
    request: Request,
    auth: AuthContext,
    service: SessionManagementService,
    umos: list[str],
    *,
    action: str = "data.manage",
) -> None:
    """Authorize every server-resolved session target for one mutation."""

    for umo in sorted(set(umos)):
        try:
            resource = Resource.session(service.resolve_umo_config_id(umo), umo)
        except (AuthorizationValueError, SessionManagementServiceError) as exc:
            raise ApiError("Invalid session target", status_code=400) from exc
        await require_resource_action(request, auth, action=action, resource=resource)


async def _group_umos_for_mutation(
    service: SessionManagementService,
    payload: dict,
    *,
    group_id: str | None = None,
) -> list[str]:
    """Return every session a group operation can read or change."""

    targets: set[str] = set()
    for key in ("umos", "add_umos", "remove_umos"):
        values = payload.get(key)
        if values:
            targets.update(service._validate_umo_list(values))
    if group_id:
        groups = await service.get_groups()
        group = groups.get(group_id)
        if group is None:
            raise SessionManagementServiceError(f"分组 '{group_id}' 不存在")
        targets.update(service._normalize_group_umos(group.get("umos", [])))
    return sorted(targets)


def _service_error(exc: SessionManagementServiceError) -> dict:
    return error(str(exc))


def _unexpected_error(prefix: str, exc: Exception):
    return internal_error_response(logger, prefix, exc)


async def _run(operation, *, label: str) -> dict | JSONResponse:
    try:
        result = await run_maybe_async(operation)
        return ok(result)
    except SessionManagementServiceError as exc:
        return _service_error(exc)
    except Exception as exc:
        return _unexpected_error(label, exc)


@router.get("/sessions")
async def list_sessions(
    page: int = Query(1),
    page_size: int = Query(20),
    search: str = Query(""),
    message_type: str = Query("all"),
    platform: str = Query(""),
    _auth: AuthContext = Depends(require_data_scope),
    service: SessionManagementService = Depends(get_service),
):
    try:
        return ok(
            await service.list_all_umos_with_status(
                page=page,
                page_size=page_size,
                search=search.strip(),
                message_type=message_type,
                platform=platform,
            )
        )
    except SessionManagementServiceError as exc:
        return _service_error(exc)
    except Exception as exc:
        return _unexpected_error("获取会话状态列表失败", exc)


@router.get("/sessions/active-umos")
async def list_active_umos(
    _auth: AuthContext = Depends(require_data_scope),
    service: SessionManagementService = Depends(get_service),
):
    try:
        return ok(await service.list_active_umos())
    except SessionManagementServiceError as exc:
        return _service_error(exc)
    except Exception as exc:
        return _unexpected_error("获取 UMO 列表失败", exc)


@router.get("/sessions/rules")
async def list_session_rules(
    page: int = Query(1),
    page_size: int = Query(10),
    search: str = Query(""),
    _auth: AuthContext = Depends(require_data_scope),
    service: SessionManagementService = Depends(get_service),
):
    try:
        return ok(
            await service.list_session_rules(
                page=page,
                page_size=page_size,
                search=search.strip(),
            )
        )
    except SessionManagementServiceError as exc:
        return _service_error(exc)
    except Exception as exc:
        return _unexpected_error("获取规则列表失败", exc)


@router.post("/sessions/rules")
async def update_session_rule(
    payload: SessionRuleRequest,
    request: Request,
    auth: AuthContext = Depends(require_data_scope),
    service: SessionManagementService = Depends(get_service),
):
    try:
        body = payload.model_dump(exclude_none=True)
        await _authorize_session_umos(
            request, auth, service, await _payload_umos(service, body)
        )
        return ok(await service.update_session_rule(body))
    except ApiError:
        raise
    except SessionManagementServiceError as exc:
        return _service_error(exc)
    except Exception as exc:
        return _unexpected_error("更新会话规则失败", exc)


@router.post("/sessions/rules/delete")
async def delete_session_rule(
    payload: UmoListRequest,
    request: Request,
    auth: AuthContext = Depends(require_data_scope),
    service: SessionManagementService = Depends(get_service),
):
    try:
        body = payload.model_dump(exclude_none=True)
        await _authorize_session_umos(
            request, auth, service, await _payload_umos(service, body)
        )
        return ok(await service.delete_session_rules(body))
    except ApiError:
        raise
    except SessionManagementServiceError as exc:
        return _service_error(exc)
    except Exception as exc:
        return _unexpected_error("删除会话规则失败", exc)


@router.patch("/sessions/provider")
async def update_session_provider(
    payload: BatchSessionProviderRequest,
    request: Request,
    auth: AuthContext = Depends(require_data_scope),
    service: SessionManagementService = Depends(get_service),
):
    try:
        body = payload.model_dump(exclude_none=True)
        await _authorize_session_umos(
            request, auth, service, await _payload_umos(service, body)
        )
        return ok(await service.batch_update_provider(body))
    except ApiError:
        raise
    except SessionManagementServiceError as exc:
        return _service_error(exc)
    except Exception as exc:
        return _unexpected_error("批量更新 Provider 失败", exc)


@router.patch("/sessions/service")
async def update_session_service(
    payload: BatchSessionServiceRequest,
    request: Request,
    auth: AuthContext = Depends(require_data_scope),
    service: SessionManagementService = Depends(get_service),
):
    try:
        body = payload.model_dump(exclude_none=True)
        await _authorize_session_umos(
            request, auth, service, await _payload_umos(service, body)
        )
        return ok(await service.batch_update_service(body))
    except ApiError:
        raise
    except SessionManagementServiceError as exc:
        return _service_error(exc)
    except Exception as exc:
        return _unexpected_error("批量更新服务状态失败", exc)


@router.get("/session-groups")
async def list_session_groups(
    _auth: AuthContext = Depends(require_data_scope),
    service: SessionManagementService = Depends(get_service),
):
    try:
        return ok(await service.list_groups())
    except SessionManagementServiceError as exc:
        return _service_error(exc)
    except Exception as exc:
        return _unexpected_error("获取分组列表失败", exc)


@router.post("/session-groups")
async def create_session_group(
    payload: SessionGroupRequest,
    request: Request,
    auth: AuthContext = Depends(require_data_scope),
    service: SessionManagementService = Depends(get_service),
):
    try:
        body = payload.model_dump(exclude_none=True)
        await _authorize_session_umos(
            request,
            auth,
            service,
            await _group_umos_for_mutation(service, body),
        )
        return ok(await service.create_group(body))
    except ApiError:
        raise
    except SessionManagementServiceError as exc:
        return _service_error(exc)
    except Exception as exc:
        return _unexpected_error("创建分组失败", exc)


@router.put("/session-groups/{group_id}")
async def update_session_group(
    group_id: str,
    payload: SessionGroupRequest,
    request: Request,
    auth: AuthContext = Depends(require_data_scope),
    service: SessionManagementService = Depends(get_service),
):
    try:
        body = payload.model_dump(exclude_none=True)
        await _authorize_session_umos(
            request,
            auth,
            service,
            await _group_umos_for_mutation(service, body, group_id=group_id),
        )
        return ok(await service.update_group({"group_id": group_id, **body}))
    except ApiError:
        raise
    except SessionManagementServiceError as exc:
        return _service_error(exc)
    except Exception as exc:
        return _unexpected_error("更新分组失败", exc)


@router.delete("/session-groups/{group_id}")
async def delete_session_group(
    group_id: str,
    request: Request,
    auth: AuthContext = Depends(require_data_scope),
    service: SessionManagementService = Depends(get_service),
):
    try:
        await _authorize_session_umos(
            request,
            auth,
            service,
            await _group_umos_for_mutation(service, {}, group_id=group_id),
        )
        return ok(await service.delete_group({"group_id": group_id}))
    except ApiError:
        raise
    except SessionManagementServiceError as exc:
        return _service_error(exc)
    except Exception as exc:
        return _unexpected_error("删除分组失败", exc)
