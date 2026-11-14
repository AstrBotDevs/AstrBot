"""Authenticated management of reusable agent configurations."""

from fastapi import APIRouter, Depends, Request

from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import AgentConfigRequest
from astrbot.dashboard.services.agent_config_service import AgentConfigService

from .auth import ScopeDependency

router = APIRouter(
    tags=["Agent Configurations"], dependencies=[Depends(ScopeDependency("config"))]
)


def get_service(request: Request) -> AgentConfigService:
    return request.app.state.services.agent_configs


@router.get("/agent-configs")
async def list_agent_configs(
    service: AgentConfigService = Depends(get_service),
) -> dict:
    return ok(await service.list())


@router.get("/agent-configs/{config_id}")
async def get_agent_config(
    config_id: str, service: AgentConfigService = Depends(get_service)
) -> dict:
    try:
        return ok((await service.store.get(config_id)).model_dump())
    except ValueError as exc:
        raise ApiError(str(exc), status_code=404) from exc


@router.post("/agent-configs")
async def create_agent_config(
    payload: AgentConfigRequest, service: AgentConfigService = Depends(get_service)
) -> dict:
    try:
        return ok(await service.save(payload.model_dump()))
    except ValueError as exc:
        raise ApiError(str(exc)) from exc


@router.put("/agent-configs/{config_id}")
async def update_agent_config(
    config_id: str,
    payload: AgentConfigRequest,
    service: AgentConfigService = Depends(get_service),
) -> dict:
    try:
        return ok(await service.save(payload.model_dump(), config_id))
    except ValueError as exc:
        raise ApiError(str(exc)) from exc


@router.delete("/agent-configs/{config_id}")
async def delete_agent_config(
    config_id: str, service: AgentConfigService = Depends(get_service)
) -> dict:
    try:
        await service.delete(config_id)
        return ok()
    except ValueError as exc:
        raise ApiError(str(exc), status_code=404) from exc


@router.get("/agent-runtimes")
async def list_agent_runtimes(
    service: AgentConfigService = Depends(get_service),
) -> dict:
    return ok(service.runtimes())
