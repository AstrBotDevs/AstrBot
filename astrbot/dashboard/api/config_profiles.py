from typing import Any

from fastapi import APIRouter, Depends, Request

from astrbot.dashboard.responses import error, ok
from astrbot.dashboard.schemas import (
    ConfigContentRequest,
    ConfigProfileCreateRequest,
    ConfigRoutesReplaceRequest,
    ConfigRouteUpsertRequest,
    RenameRequest,
)
from astrbot.dashboard.services.api_key_scopes import api_key_has_scope
from astrbot.dashboard.services.config_service import (
    ConfigDisplayService,
    ConfigFileService,
    ConfigProfileService,
    ConfigRoutingService,
)

from .auth import AuthContext, require_scope

router = APIRouter(tags=["Config Profiles"])


async def require_config_scope(request: Request) -> AuthContext:
    return await require_scope(request, "config")


def get_service(request: Request) -> ConfigProfileService:
    return request.app.state.services.config_profiles


def get_routing_service(request: Request) -> ConfigRoutingService:
    return request.app.state.services.config_routes


def get_display_service(request: Request) -> ConfigDisplayService:
    return request.app.state.services.config_display


def get_file_service(request: Request) -> ConfigFileService:
    return request.app.state.services.config_files


async def _json_or_empty(request: Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _alias_error(message: str):
    return error(message)


def _model_dict(payload) -> dict[str, Any]:
    return payload.model_dump(exclude_none=True)


def _can_edit_admin_ids(auth: AuthContext) -> bool:
    return auth.via != "api_key" or api_key_has_scope(auth.scopes, "config:edit_admin")


@router.get("/config-profiles/schema")
async def get_config_profile_schema(
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    return ok(service.get_profile_schema())


@router.get("/config-profiles")
async def list_config_profiles(
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    return ok(service.list_profiles())


@router.post(
    "/config-profiles",
    openapi_extra={"x-astrbot-sensitive-scopes": ["config:edit_admin"]},
)
async def create_config_profile(
    payload: ConfigProfileCreateRequest,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    return ok(
        await service.create_profile(
            payload.name,
            payload.config,
            allow_admin_id_change=_can_edit_admin_ids(auth),
        ),
        "创建成功",
    )


@router.get("/config-profiles/{config_id}")
async def get_config_profile(
    config_id: str,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    return ok(service.get_profile(config_id))


@router.put(
    "/config-profiles/{config_id}",
    openapi_extra={"x-astrbot-sensitive-scopes": ["config:edit_admin"]},
)
async def update_config_profile(
    config_id: str,
    payload: ConfigContentRequest,
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    message = await service.update_profile(
        config_id,
        _model_dict(payload),
        subject=auth.subject,
        two_factor_code=request.headers.get("X-2FA-Code"),
        allow_admin_id_change=_can_edit_admin_ids(auth),
    )
    return ok(message=message or "保存成功")


@router.patch("/config-profiles/{config_id}")
async def rename_config_profile(
    config_id: str,
    payload: RenameRequest,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    await service.rename_profile(config_id, payload.name)
    return ok(message="更新成功")


@router.delete("/config-profiles/{config_id}")
async def delete_config_profile(
    config_id: str,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    await service.delete_profile(config_id)
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
    return ok(service.get_system_config())


@router.get("/system-config/runtime")
async def get_system_config_runtime(
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigDisplayService = Depends(get_display_service),
):
    return ok(await service.get_configs())


@router.put(
    "/system-config",
    openapi_extra={"x-astrbot-sensitive-scopes": ["config:edit_admin"]},
)
async def update_system_config(
    payload: ConfigContentRequest,
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    message = await service.update_profile(
        "default",
        _model_dict(payload),
        subject=auth.subject,
        two_factor_code=request.headers.get("X-2FA-Code"),
        allow_admin_id_change=_can_edit_admin_ids(auth),
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
