from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from astrbot.core import logger
from astrbot.dashboard.services.session_management_service import (
    SessionManagementService,
    SessionManagementServiceError,
)

from ...auth import AuthContext
from ...responses import error, ok
from ...schemas import (
    BatchSessionProviderRequest,
    BatchSessionServiceRequest,
    SessionGroupRequest,
    SessionRuleRequest,
    UmoListRequest,
)
from .common import require_data_scope

router = APIRouter(tags=["Sessions"])


def get_service(request: Request) -> SessionManagementService:
    return request.app.state.services.sessions


def _service_error(exc: SessionManagementServiceError) -> dict:
    return error(str(exc))


def _unexpected_error(prefix: str, exc: Exception) -> dict:
    logger.error(f"{prefix}: {exc!s}")
    return error(f"{prefix}: {exc!s}")


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
    _auth: AuthContext = Depends(require_data_scope),
    service: SessionManagementService = Depends(get_service),
):
    try:
        return ok(
            await service.update_session_rule(payload.model_dump(exclude_none=True))
        )
    except SessionManagementServiceError as exc:
        return _service_error(exc)
    except Exception as exc:
        return _unexpected_error("更新会话规则失败", exc)


@router.post("/sessions/rules/delete")
async def delete_session_rule(
    payload: UmoListRequest,
    _auth: AuthContext = Depends(require_data_scope),
    service: SessionManagementService = Depends(get_service),
):
    try:
        return ok(
            await service.delete_session_rules(payload.model_dump(exclude_none=True))
        )
    except SessionManagementServiceError as exc:
        return _service_error(exc)
    except Exception as exc:
        return _unexpected_error("删除会话规则失败", exc)


@router.patch("/sessions/provider")
async def update_session_provider(
    payload: BatchSessionProviderRequest,
    _auth: AuthContext = Depends(require_data_scope),
    service: SessionManagementService = Depends(get_service),
):
    try:
        return ok(
            await service.batch_update_provider(payload.model_dump(exclude_none=True))
        )
    except SessionManagementServiceError as exc:
        return _service_error(exc)
    except Exception as exc:
        return _unexpected_error("批量更新 Provider 失败", exc)


@router.patch("/sessions/service")
async def update_session_service(
    payload: BatchSessionServiceRequest,
    _auth: AuthContext = Depends(require_data_scope),
    service: SessionManagementService = Depends(get_service),
):
    try:
        return ok(
            await service.batch_update_service(payload.model_dump(exclude_none=True))
        )
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
        return ok(service.list_groups())
    except SessionManagementServiceError as exc:
        return _service_error(exc)
    except Exception as exc:
        return _unexpected_error("获取分组列表失败", exc)


@router.post("/session-groups")
async def create_session_group(
    payload: SessionGroupRequest,
    _auth: AuthContext = Depends(require_data_scope),
    service: SessionManagementService = Depends(get_service),
):
    try:
        return ok(service.create_group(payload.model_dump(exclude_none=True)))
    except SessionManagementServiceError as exc:
        return _service_error(exc)
    except Exception as exc:
        return _unexpected_error("创建分组失败", exc)


@router.put("/session-groups/{group_id}")
async def update_session_group(
    group_id: str,
    payload: SessionGroupRequest,
    _auth: AuthContext = Depends(require_data_scope),
    service: SessionManagementService = Depends(get_service),
):
    try:
        body = payload.model_dump(exclude_none=True)
        return ok(service.update_group({"group_id": group_id, **body}))
    except SessionManagementServiceError as exc:
        return _service_error(exc)
    except Exception as exc:
        return _unexpected_error("更新分组失败", exc)


@router.delete("/session-groups/{group_id}")
async def delete_session_group(
    group_id: str,
    _auth: AuthContext = Depends(require_data_scope),
    service: SessionManagementService = Depends(get_service),
):
    try:
        return ok(service.delete_group({"group_id": group_id}))
    except SessionManagementServiceError as exc:
        return _service_error(exc)
    except Exception as exc:
        return _unexpected_error("删除分组失败", exc)
