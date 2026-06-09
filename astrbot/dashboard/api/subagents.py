from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import SubAgentConfigRequest
from astrbot.dashboard.services.subagent_service import (
    SubAgentService,
    SubAgentServiceError,
)

from .auth import AuthContext, require_dashboard_user, require_scope

router = APIRouter(tags=["Subagents"])
legacy_router = APIRouter(
    prefix="/api/subagent",
    tags=["Dashboard Subagents"],
    include_in_schema=False,
)


async def require_config_scope(request: Request) -> AuthContext:
    return await require_scope(request, "config")


def get_service(request: Request) -> SubAgentService:
    return request.app.state.services.subagents


def _payload_dict(payload: SubAgentConfigRequest) -> dict:
    return payload.model_dump(exclude_none=True)


def _raise_subagent_error(exc: SubAgentServiceError) -> None:
    raise ApiError(str(exc)) from exc


async def _get_config(service: SubAgentService):
    try:
        return ok(service.get_config())
    except SubAgentServiceError as exc:
        _raise_subagent_error(exc)


async def _update_config(payload: SubAgentConfigRequest, service: SubAgentService):
    try:
        await service.update_config(_payload_dict(payload))
        return ok(message="保存成功")
    except SubAgentServiceError as exc:
        _raise_subagent_error(exc)


async def _get_available_tools(service: SubAgentService):
    try:
        return ok(service.get_available_tools())
    except SubAgentServiceError as exc:
        _raise_subagent_error(exc)


@router.get("/subagents/config")
async def get_subagent_config(
    _auth: AuthContext = Depends(require_config_scope),
    service: SubAgentService = Depends(get_service),
):
    return await _get_config(service)


@router.put("/subagents/config")
async def update_subagent_config(
    payload: SubAgentConfigRequest,
    _auth: AuthContext = Depends(require_config_scope),
    service: SubAgentService = Depends(get_service),
):
    return await _update_config(payload, service)


@router.get("/subagents/available-tools")
async def get_subagent_tools(
    _auth: AuthContext = Depends(require_config_scope),
    service: SubAgentService = Depends(get_service),
):
    return await _get_available_tools(service)


@legacy_router.get("/config")
async def get_dashboard_subagent_config(
    _username: str = Depends(require_dashboard_user),
    service: SubAgentService = Depends(get_service),
):
    return await _get_config(service)


@legacy_router.post("/config")
async def update_dashboard_subagent_config(
    payload: SubAgentConfigRequest,
    _username: str = Depends(require_dashboard_user),
    service: SubAgentService = Depends(get_service),
):
    return await _update_config(payload, service)


@legacy_router.get("/available-tools")
async def get_dashboard_subagent_tools(
    _username: str = Depends(require_dashboard_user),
    service: SubAgentService = Depends(get_service),
):
    return await _get_available_tools(service)
