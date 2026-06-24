from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from astrbot.dashboard.responses import error, ok
from astrbot.dashboard.schemas import (
    ConfigContentRequest,
    ConfigProfileCreateRequest,
    ConfigRoutesReplaceRequest,
    ConfigRouteUpsertRequest,
    RenameRequest,
)
from astrbot.dashboard.services.config_service import (
    ConfigDisplayService,
    ConfigFileService,
    ConfigProfileService,
    ConfigRoutingService,
)

from .auth import AuthContext, require_scope
from .multipart import multipart_parts

router = APIRouter(tags=["Config Profiles"])
legacy_router = APIRouter(
    prefix="/api/config",
    tags=["Dashboard Config"],
    include_in_schema=False,
)


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
    payload: ConfigContentRequest,
    request: Request,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    message = await service.update_profile(
        config_id,
        _model_dict(payload),
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
    return ok(service.get_system_config())


@router.get("/system-config/runtime")
async def get_system_config_runtime(
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigDisplayService = Depends(get_display_service),
):
    return ok(await service.get_configs())


@router.put("/system-config")
async def update_system_config(
    payload: ConfigContentRequest,
    request: Request,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    message = await service.update_profile(
        "default",
        _model_dict(payload),
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


@legacy_router.get("/default")
async def get_dashboard_alias_default_config(
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    return ok(service.get_profile_schema())


@legacy_router.get("/abconfs")
async def list_dashboard_alias_config_profiles(
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    return ok(service.list_profiles())


@legacy_router.post("/abconf/new")
async def create_dashboard_alias_config_profile(
    request: Request,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    body = await _json_or_empty(request)
    try:
        return ok(
            await service.create_profile(
                body.get("name"),
                body.get("config"),
            ),
            "创建成功",
        )
    except ValueError as exc:
        return _alias_error(str(exc))


@legacy_router.get("/abconf")
async def get_dashboard_alias_config_profile(
    id: str | None = Query(default=None),
    system_config: str = Query(default="0"),
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    if system_config.lower() == "1":
        return ok(service.get_system_schema())
    if not id:
        return _alias_error("缺少配置文件 ID")
    try:
        return ok(service.get_profile(id))
    except ValueError as exc:
        return _alias_error(str(exc))


@legacy_router.post("/abconf/delete")
async def delete_dashboard_alias_config_profile(
    request: Request,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    body = await _json_or_empty(request)
    config_id = body.get("id")
    if not config_id:
        return _alias_error("缺少配置文件 ID")
    try:
        service.delete_profile(str(config_id))
        return ok(message="删除成功")
    except ValueError as exc:
        return _alias_error(str(exc))


@legacy_router.post("/abconf/update")
async def rename_dashboard_alias_config_profile(
    request: Request,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    body = await _json_or_empty(request)
    config_id = body.get("id")
    if not config_id:
        return _alias_error("缺少配置文件 ID")
    try:
        service.rename_profile(str(config_id), body.get("name"))
        return ok(message="更新成功")
    except ValueError as exc:
        return _alias_error(str(exc))


@legacy_router.post("/astrbot/update")
async def update_dashboard_alias_astrbot_config(
    request: Request,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    body = await _json_or_empty(request)
    config = body.get("config")
    config_id = body.get("conf_id")
    if not isinstance(config, dict):
        return _alias_error("Invalid config payload")
    if not config_id:
        return _alias_error("Config file None does not exist")
    try:
        message = await service.update_profile(
            str(config_id),
            config,
            two_factor_code=request.headers.get("X-2FA-Code"),
        )
        return ok(message=message or "保存成功~")
    except ValueError as exc:
        return _alias_error(str(exc))


@legacy_router.get("/get")
async def get_dashboard_alias_configs(
    request: Request,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigDisplayService = Depends(get_display_service),
):
    try:
        return ok(await service.get_configs_from_dashboard_args(request.query_params))
    except ValueError as exc:
        return _alias_error(str(exc))


@legacy_router.post("/plugin/update")
async def update_dashboard_alias_plugin_configs(
    request: Request,
    plugin_name: str = Query(default="unknown"),
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigFileService = Depends(get_file_service),
):
    body = await _json_or_empty(request)
    try:
        message = await service.save_plugin_configs_from_dashboard_payload(
            body,
            plugin_name=plugin_name,
        )
        return ok(message=message)
    except ValueError as exc:
        return _alias_error(str(exc))


@legacy_router.post("/file/upload")
async def upload_dashboard_alias_config_file(
    request: Request,
    scope: str | None = Query(default=None),
    name: str | None = Query(default=None),
    key: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigFileService = Depends(get_file_service),
):
    _, files = await multipart_parts(request)
    try:
        return ok(
            await service.upload_config_file(
                scope=scope,
                name=name,
                key_path=key,
                files=files,
            )
        )
    except ValueError as exc:
        return _alias_error(str(exc))


@legacy_router.post("/file/delete")
async def delete_dashboard_alias_config_file(
    request: Request,
    scope: str | None = Query(default=None),
    name: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigFileService = Depends(get_file_service),
):
    body = await _json_or_empty(request)
    try:
        message = service.delete_config_file_from_dashboard_payload(
            scope=scope or "plugin",
            name=name,
            payload=body,
        )
        return ok(message=message)
    except ValueError as exc:
        return _alias_error(str(exc))


@legacy_router.get("/file/get")
async def list_dashboard_alias_config_files(
    scope: str | None = Query(default=None),
    name: str | None = Query(default=None),
    key: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigFileService = Depends(get_file_service),
):
    try:
        return ok(
            service.list_config_files(
                scope=scope,
                name=name,
                key_path=key,
            )
        )
    except ValueError as exc:
        return _alias_error(str(exc))


@legacy_router.get("/umo_abconf_routes")
async def get_dashboard_alias_config_routes(
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigRoutingService = Depends(get_routing_service),
):
    return ok(service.list_routes())


@legacy_router.post("/umo_abconf_route/update_all")
async def update_dashboard_alias_config_routes(
    request: Request,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigRoutingService = Depends(get_routing_service),
):
    body = await _json_or_empty(request)
    try:
        await service.replace_routes(body)
    except ValueError:
        return _alias_error("缺少或错误的路由表数据")
    return ok(message="更新成功")


@legacy_router.post("/umo_abconf_route/update")
async def upsert_dashboard_alias_config_route(
    request: Request,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigRoutingService = Depends(get_routing_service),
):
    body = await _json_or_empty(request)
    try:
        await service.upsert_route(body)
    except ValueError:
        return _alias_error("缺少 UMO 或配置文件 ID")
    return ok(message="更新成功")


@legacy_router.post("/umo_abconf_route/delete")
async def delete_dashboard_alias_config_route(
    request: Request,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigRoutingService = Depends(get_routing_service),
):
    body = await _json_or_empty(request)
    try:
        await service.delete_route(body)
    except ValueError:
        return _alias_error("缺少 UMO")
    return ok(message="删除成功")
