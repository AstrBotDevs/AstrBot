from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from astrbot.dashboard.services.config_service import (
    ConfigProfileService,
    ConfigRoutingService,
)

from ..auth import AuthContext, require_scope
from ..responses import ok
from ..schemas import (
    ConfigProfileCreateRequest,
    ConfigRoutesReplaceRequest,
    ConfigRouteUpsertRequest,
    RenameRequest,
)

router = APIRouter(tags=["Config Profiles"])


async def require_config_scope(request: Request) -> AuthContext:
    return await require_scope(request, "config")


def get_service(request: Request) -> ConfigProfileService:
    return request.app.state.services.config_profiles


def get_routing_service(request: Request) -> ConfigRoutingService:
    return request.app.state.services.config_routes


@router.get("/config-profiles/schema")
async def get_config_profile_schema(
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    return ok(service.get_profile_schema())


@router.get("/config-profiles")
async def list_config_profiles(
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    return ok(service.list_profiles())


@router.post("/config-profiles")
async def create_config_profile(
    payload: ConfigProfileCreateRequest,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    return ok(await service.create_profile(payload.name, payload.config), "创建成功")


@router.get("/config-profiles/{config_id}")
async def get_config_profile(
    config_id: str,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    return ok(service.get_profile(config_id))


@router.put("/config-profiles/{config_id}")
async def update_config_profile(
    config_id: str,
    payload: dict[str, Any],
    request: Request,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    message = await service.update_profile(
        config_id,
        payload,
        two_factor_code=request.headers.get("X-2FA-Code"),
    )
    return ok(message=message or "保存成功")


@router.patch("/config-profiles/{config_id}")
async def rename_config_profile(
    config_id: str,
    payload: RenameRequest,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    service.rename_profile(config_id, payload.name)
    return ok(message="更新成功")


@router.delete("/config-profiles/{config_id}")
async def delete_config_profile(
    config_id: str,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    service.delete_profile(config_id)
    return ok(message="删除成功")


@router.get("/system-config/schema")
async def get_system_config_schema(
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    return ok(service.get_system_schema())


@router.get("/system-config")
async def get_system_config(
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    return ok(service.get_profile("default"))


@router.put("/system-config")
async def update_system_config(
    payload: dict[str, Any],
    request: Request,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    message = await service.update_profile(
        "default",
        payload,
        two_factor_code=request.headers.get("X-2FA-Code"),
    )
    return ok(message=message or "保存成功")


@router.get("/config-routes")
async def list_config_routes(
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigRoutingService = Depends(get_routing_service),
):
    return ok(service.list_routes())


@router.put("/config-routes")
async def replace_config_routes(
    payload: ConfigRoutesReplaceRequest,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigRoutingService = Depends(get_routing_service),
):
    await service.replace_route_mapping(payload.routing)
    return ok(message="更新成功")


@router.put("/config-routes/{umo}")
async def upsert_config_route(
    umo: str,
    payload: ConfigRouteUpsertRequest,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigRoutingService = Depends(get_routing_service),
):
    await service.set_route(umo, payload.config_id)
    return ok(message="更新成功")


@router.delete("/config-routes/{umo}")
async def delete_config_route(
    umo: str,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigRoutingService = Depends(get_routing_service),
):
    await service.delete_route_by_umo(umo)
    return ok(message="删除成功")
