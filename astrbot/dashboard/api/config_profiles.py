from typing import Any

from fastapi import APIRouter, Depends, Request

from astrbot.core.auth.models import Resource
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
    sensitive_config_changed,
)

from .auth import AuthContext, require_resource_action, require_scope

router = APIRouter(tags=["Config Profiles"])


async def require_config_scope(request: Request) -> AuthContext:
    return await require_scope(request, "config", authorize_action=False)


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


async def _authorize_config_resource(
    request: Request,
    auth: AuthContext,
    *,
    config_id: str,
    write: bool = False,
) -> None:
    await require_resource_action(
        request,
        auth,
        action="platform.manage" if write else "platform.read",
        resource=Resource.instance(config_id),
    )


async def _authorize_config_credentials_if_changed(
    request: Request,
    auth: AuthContext,
    *,
    config_id: str,
    posted_config: dict | None,
    service: ConfigProfileService,
    missing_is_change: bool = True,
) -> None:
    if not isinstance(posted_config, dict):
        return
    current_config = service.acm.confs.get(config_id)
    if not isinstance(current_config, dict) or not sensitive_config_changed(
        current_config,
        posted_config,
        missing_is_change=missing_is_change,
        ignored_paths=(
            ("dashboard", "totp", "enable"),
            ("dashboard", "totp", "secret"),
            ("dashboard", "totp", "recovery_code_hash"),
        ),
    ):
        return
    await require_resource_action(
        request,
        auth,
        action="provider.credentials.write",
        resource=Resource.instance(config_id),
    )


@router.get("/config-profiles/schema")
async def get_config_profile_schema(
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    await _authorize_config_resource(request, auth, config_id="default")
    return ok(service.get_profile_schema())


@router.get("/config-profiles")
async def list_config_profiles(
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    await _authorize_config_resource(request, auth, config_id="default")
    return ok(service.list_profiles())


@router.post("/config-profiles")
async def create_config_profile(
    payload: ConfigProfileCreateRequest,
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    await require_resource_action(
        request,
        auth,
        action="platform.manage",
        resource=Resource.named("config-profile", "collection", config_id="default"),
    )
    await _authorize_config_credentials_if_changed(
        request,
        auth,
        config_id="default",
        posted_config=payload.config,
        service=service,
        missing_is_change=False,
    )
    return ok(
        await service.create_profile(
            payload.name,
            payload.config,
        ),
        "创建成功",
    )


@router.get("/config-profiles/{config_id}")
async def get_config_profile(
    config_id: str,
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    await _authorize_config_resource(request, auth, config_id=config_id)
    return ok(service.get_profile(config_id))


@router.put("/config-profiles/{config_id}")
async def update_config_profile(
    config_id: str,
    payload: ConfigContentRequest,
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    await _authorize_config_resource(request, auth, config_id=config_id, write=True)
    posted_config = _model_dict(payload)
    await _authorize_config_credentials_if_changed(
        request,
        auth,
        config_id=config_id,
        posted_config=posted_config,
        service=service,
    )
    message = await service.update_profile(
        config_id,
        posted_config,
        subject=auth.subject,
        two_factor_code=request.headers.get("X-2FA-Code"),
    )
    return ok(message=message or "保存成功")


@router.patch("/config-profiles/{config_id}")
async def rename_config_profile(
    config_id: str,
    payload: RenameRequest,
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    await _authorize_config_resource(request, auth, config_id=config_id, write=True)
    await service.rename_profile(config_id, payload.name)
    return ok(message="更新成功")


@router.delete("/config-profiles/{config_id}")
async def delete_config_profile(
    config_id: str,
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    await _authorize_config_resource(request, auth, config_id=config_id, write=True)
    await service.delete_profile(config_id)
    return ok(message="删除成功")


@router.get("/system-config/schema")
async def get_system_config_schema(
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    await _authorize_config_resource(request, auth, config_id="default")
    return ok(service.get_system_schema())


@router.get("/system-config")
async def get_system_config(
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    await _authorize_config_resource(request, auth, config_id="default")
    return ok(service.get_system_config())


@router.get("/system-config/runtime")
async def get_system_config_runtime(
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigDisplayService = Depends(get_display_service),
):
    await _authorize_config_resource(request, auth, config_id="default")
    return ok(await service.get_configs())


@router.put("/system-config")
async def update_system_config(
    payload: ConfigContentRequest,
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    await _authorize_config_resource(request, auth, config_id="default", write=True)
    posted_config = _model_dict(payload)
    await _authorize_config_credentials_if_changed(
        request,
        auth,
        config_id="default",
        posted_config=posted_config,
        service=service,
    )
    message = await service.update_profile(
        "default",
        posted_config,
        subject=auth.subject,
        two_factor_code=request.headers.get("X-2FA-Code"),
    )
    return ok(message=message or "保存成功")


@router.get("/config-routes")
async def list_config_routes(
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigRoutingService = Depends(get_routing_service),
):
    await require_resource_action(
        request,
        auth,
        action="platform.read",
        resource=Resource.named("config-route", "collection", config_id="default"),
    )
    return ok(service.list_routes())


@router.put("/config-routes")
async def replace_config_routes(
    payload: ConfigRoutesReplaceRequest,
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigRoutingService = Depends(get_routing_service),
):
    for config_id in set(payload.routing.values()):
        await _authorize_config_resource(request, auth, config_id=config_id, write=True)
    await service.replace_route_mapping(payload.routing)
    return ok(message="更新成功")


@router.put("/config-routes/{umo}")
async def upsert_config_route(
    umo: str,
    payload: ConfigRouteUpsertRequest,
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigRoutingService = Depends(get_routing_service),
):
    await _authorize_config_resource(
        request, auth, config_id=payload.config_id, write=True
    )
    await service.set_route(umo, payload.config_id)
    return ok(message="更新成功")


@router.delete("/config-routes/{umo}")
async def delete_config_route(
    umo: str,
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigRoutingService = Depends(get_routing_service),
):
    await require_resource_action(
        request,
        auth,
        action="platform.manage",
        resource=Resource.named("config-route", umo, config_id="default"),
    )
    await service.delete_route_by_umo(umo)
    return ok(message="删除成功")
