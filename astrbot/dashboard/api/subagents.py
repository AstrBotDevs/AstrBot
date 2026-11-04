from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, Depends, Request

from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.services.subagent_service import (
    SubAgentService,
    SubAgentServiceError,
)

from .auth import AuthContext, ScopeDependency, require_dashboard_user

router = APIRouter(tags=["Subagents"])
legacy_router = APIRouter(
    prefix="/api/subagent",
    tags=["Dashboard Subagents"],
    include_in_schema=False,
)


require_config_scope = ScopeDependency("config")


def get_service(request: Request) -> SubAgentService:
    return request.app.state.services.subagents


def _raise_subagent_error(exc: SubAgentServiceError) -> NoReturn:
    raise ApiError(str(exc)) from exc


async def _get_available_tools(service: SubAgentService) -> dict[str, Any]:
    try:
        return ok(service.get_available_tools())
    except SubAgentServiceError as exc:
        _raise_subagent_error(exc)


@router.get("/subagents/available-tools")
async def get_subagent_tools(
    _auth: AuthContext = Depends(require_config_scope),
    service: SubAgentService = Depends(get_service),
) -> dict[str, Any]:
    return await _get_available_tools(service)


@legacy_router.get("/available-tools")
async def get_dashboard_subagent_tools(
    _username: str = Depends(require_dashboard_user),
    service: SubAgentService = Depends(get_service),
) -> dict[str, Any]:
    return await _get_available_tools(service)
