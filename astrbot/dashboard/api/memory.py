from typing import Any

from fastapi import APIRouter, Body, Depends, Request

from astrbot import logger
from astrbot.core.auth.models import Resource
from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.responses import error, ok
from astrbot.dashboard.schemas import (
    MemoryFactActionRequest,
    MemoryFactCreateRequest,
    MemoryFactPatchRequest,
    MemoryProfileRefreshRequest,
)
from astrbot.dashboard.services.memory_service import MemoryService, MemoryServiceError

from .auth import AuthContext, object_resource, require_resource_action, require_scope
from .error_handling import internal_error_response

router = APIRouter(tags=["Memory"])


def get_service(request: Request) -> MemoryService:
    return request.app.state.services.memory


async def require_memory_scope(request: Request) -> AuthContext:
    auth = await require_scope(request, "memory")
    path_params = request.path_params
    if fact_id := path_params.get("fact_id"):
        resource = object_resource("memory-fact", fact_id)
    elif person_id := path_params.get("person_id"):
        resource = object_resource("memory-profile", person_id)
    else:
        resource = Resource.named("memory", "collection")
    await require_resource_action(
        request,
        auth,
        action="data.manage",
        resource=resource,
    )
    return auth


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except TypeError, ValueError:
        return default


async def _run(operation, *, prefix: str):
    try:
        result = await run_maybe_async(operation)
        if isinstance(result, tuple):
            data, message = result
            return ok(data, message)
        return ok(result)
    except MemoryServiceError as exc:
        return error(str(exc))
    except Exception as exc:
        return internal_error_response(logger, prefix, exc)


@router.get("/memory/facts")
async def list_memory_facts(
    request: Request,
    _auth: AuthContext = Depends(require_memory_scope),
    service: MemoryService = Depends(get_service),
):
    return await _run(
        lambda: service.list_facts(
            page=_to_int(request.query_params.get("page"), 1),
            page_size=_to_int(request.query_params.get("page_size"), 20),
            person_id=request.query_params.get("person_id"),
            chat_id=request.query_params.get("chat_id"),
            scope_id=request.query_params.get("scope_id"),
            status=request.query_params.get("status", "active"),
            query=request.query_params.get("query")
            or request.query_params.get("keyword"),
        ),
        prefix="获取记忆列表失败",
    )


@router.get("/memory/facts/{fact_id}")
async def get_memory_fact(
    fact_id: int,
    _auth: AuthContext = Depends(require_memory_scope),
    service: MemoryService = Depends(get_service),
):
    return await _run(
        lambda: service.get_fact(fact_id),
        prefix="获取记忆详情失败",
    )


@router.post("/memory/facts")
async def create_memory_fact(
    payload: MemoryFactCreateRequest,
    auth: AuthContext = Depends(require_memory_scope),
    service: MemoryService = Depends(get_service),
):
    return await _run(
        lambda: service.create_fact(
            payload.model_dump(exclude_none=True),
            operator=auth.username,
        ),
        prefix="创建记忆失败",
    )


@router.patch("/memory/facts/{fact_id}")
async def update_memory_fact(
    fact_id: int,
    payload: MemoryFactPatchRequest,
    auth: AuthContext = Depends(require_memory_scope),
    service: MemoryService = Depends(get_service),
):
    return await _run(
        lambda: service.update_fact(
            fact_id,
            payload.model_dump(exclude_none=True),
            operator=auth.username,
        ),
        prefix="更新记忆失败",
    )


@router.post("/memory/facts/{fact_id}/delete")
async def delete_memory_fact(
    fact_id: int,
    payload: MemoryFactActionRequest | None = None,
    auth: AuthContext = Depends(require_memory_scope),
    service: MemoryService = Depends(get_service),
):
    body = payload.model_dump(exclude_none=True) if payload else {}
    return await _run(
        lambda: service.set_fact_status(
            fact_id,
            status="deleted",
            operator=auth.username,
            reason=body.get("reason"),
        ),
        prefix="删除记忆失败",
    )


@router.post("/memory/facts/{fact_id}/restore")
async def restore_memory_fact(
    fact_id: int,
    payload: MemoryFactActionRequest | None = None,
    auth: AuthContext = Depends(require_memory_scope),
    service: MemoryService = Depends(get_service),
):
    body = payload.model_dump(exclude_none=True) if payload else {}
    return await _run(
        lambda: service.set_fact_status(
            fact_id,
            status="active",
            operator=auth.username,
            reason=body.get("reason"),
        ),
        prefix="恢复记忆失败",
    )


@router.get("/memory/profiles")
async def list_memory_profiles(
    request: Request,
    _auth: AuthContext = Depends(require_memory_scope),
    service: MemoryService = Depends(get_service),
):
    return await _run(
        lambda: service.list_profiles(
            page=_to_int(request.query_params.get("page"), 1),
            page_size=_to_int(request.query_params.get("page_size"), 20),
            person_id=request.query_params.get("person_id"),
            chat_scope=request.query_params.get("chat_scope")
            or request.query_params.get("scope_id"),
        ),
        prefix="获取画像列表失败",
    )


@router.post("/memory/profiles/{person_id}/refresh")
async def refresh_memory_profile(
    person_id: str,
    payload: MemoryProfileRefreshRequest | None = Body(default=None),
    auth: AuthContext = Depends(require_memory_scope),
    service: MemoryService = Depends(get_service),
):
    body = payload.model_dump(exclude_none=True) if payload else {}
    return await _run(
        lambda: service.refresh_profile(
            person_id,
            body,
            operator=auth.username,
        ),
        prefix="刷新画像失败",
    )


@router.get("/memory/operations")
async def list_memory_operations(
    request: Request,
    _auth: AuthContext = Depends(require_memory_scope),
    service: MemoryService = Depends(get_service),
):
    return await _run(
        lambda: service.list_operations(
            page=_to_int(request.query_params.get("page"), 1),
            page_size=_to_int(request.query_params.get("page_size"), 20),
            target_type=request.query_params.get("target_type"),
            target_id=request.query_params.get("target_id"),
        ),
        prefix="获取记忆操作记录失败",
    )


@router.get("/memory/stats")
async def get_memory_stats(
    _auth: AuthContext = Depends(require_memory_scope),
    service: MemoryService = Depends(get_service),
):
    return await _run(service.stats, prefix="获取记忆状态失败")
