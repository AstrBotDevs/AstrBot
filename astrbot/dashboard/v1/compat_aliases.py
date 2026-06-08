from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from astrbot.dashboard.services.config_service import (
    BotConfigService,
    ConfigProfileService,
    ConfigRoutingService,
    ProviderConfigService,
)

from .auth import AuthContext, require_scope
from .responses import error, ok
from .schemas import BotConfigRequest, ProviderConfigRequest, ProviderSourceRequest

router = APIRouter(
    prefix="/api",
    tags=["Compatibility Aliases"],
    include_in_schema=False,
)


async def require_config_scope(request: Request) -> AuthContext:
    return await require_scope(request, "config")


def get_config_profile_service(request: Request) -> ConfigProfileService:
    return request.app.state.services.config_profiles


def get_config_routing_service(request: Request) -> ConfigRoutingService:
    return request.app.state.services.config_routes


def get_bot_service(request: Request) -> BotConfigService:
    return request.app.state.services.bots


def get_provider_service(request: Request) -> ProviderConfigService:
    return request.app.state.services.providers


async def _json_or_empty(request: Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _compat_error(message: str):
    return error(message)


@router.get("/config/default")
async def get_legacy_default_config(
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_config_profile_service),
):
    return ok(service.get_profile_schema())


@router.get("/config/abconfs")
async def list_legacy_config_profiles(
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_config_profile_service),
):
    return ok(service.list_profiles())


@router.post("/config/abconf/new")
async def create_legacy_config_profile(
    request: Request,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_config_profile_service),
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
        return _compat_error(str(exc))


@router.get("/config/abconf")
async def get_legacy_config_profile(
    id: str | None = Query(default=None),
    system_config: str = Query(default="0"),
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_config_profile_service),
):
    if system_config.lower() == "1":
        return ok(service.get_system_schema())
    if not id:
        return _compat_error("缺少配置文件 ID")
    try:
        return ok(service.get_profile(id))
    except ValueError as exc:
        return _compat_error(str(exc))


@router.post("/config/abconf/delete")
async def delete_legacy_config_profile(
    request: Request,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_config_profile_service),
):
    body = await _json_or_empty(request)
    config_id = body.get("id")
    if not config_id:
        return _compat_error("缺少配置文件 ID")
    try:
        service.delete_profile(str(config_id))
        return ok(message="删除成功")
    except ValueError as exc:
        return _compat_error(str(exc))


@router.post("/config/abconf/update")
async def rename_legacy_config_profile(
    request: Request,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_config_profile_service),
):
    body = await _json_or_empty(request)
    config_id = body.get("id")
    if not config_id:
        return _compat_error("缺少配置文件 ID")
    try:
        service.rename_profile(str(config_id), body.get("name"))
        return ok(message="更新成功")
    except ValueError as exc:
        return _compat_error(str(exc))


@router.post("/config/astrbot/update")
async def update_legacy_astrbot_config(
    request: Request,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_config_profile_service),
):
    body = await _json_or_empty(request)
    config = body.get("config")
    config_id = body.get("conf_id")
    if not isinstance(config, dict):
        return _compat_error("Invalid config payload")
    if not config_id:
        return _compat_error("Config file None does not exist")
    try:
        message = await service.update_profile(
            str(config_id),
            config,
            two_factor_code=request.headers.get("X-2FA-Code"),
        )
        return ok(message=message or "保存成功~")
    except ValueError as exc:
        return _compat_error(str(exc))


@router.get("/config/umo_abconf_routes")
async def get_legacy_config_routes(
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigRoutingService = Depends(get_config_routing_service),
):
    return ok(service.list_routes())


@router.post("/config/umo_abconf_route/update_all")
async def update_legacy_config_routes(
    request: Request,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigRoutingService = Depends(get_config_routing_service),
):
    body = await _json_or_empty(request)
    try:
        await service.replace_routes(body)
    except ValueError:
        return _compat_error("缺少或错误的路由表数据")
    return ok(message="更新成功")


@router.post("/config/umo_abconf_route/update")
async def upsert_legacy_config_route(
    request: Request,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigRoutingService = Depends(get_config_routing_service),
):
    body = await _json_or_empty(request)
    try:
        await service.upsert_route(body)
    except ValueError:
        return _compat_error("缺少 UMO 或配置文件 ID")
    return ok(message="更新成功")


@router.post("/config/umo_abconf_route/delete")
async def delete_legacy_config_route(
    request: Request,
    _auth: AuthContext = Depends(require_config_scope),
    service: ConfigRoutingService = Depends(get_config_routing_service),
):
    body = await _json_or_empty(request)
    try:
        await service.delete_route(body)
    except ValueError:
        return _compat_error("缺少 UMO")
    return ok(message="删除成功")


@router.get("/config/platform/list")
async def list_legacy_platforms(
    _auth: AuthContext = Depends(require_config_scope),
    service: BotConfigService = Depends(get_bot_service),
):
    return ok({"platforms": service.list_bots()["bots"]})


@router.post("/config/platform/new")
async def create_legacy_platform(
    payload: BotConfigRequest,
    _auth: AuthContext = Depends(require_config_scope),
    service: BotConfigService = Depends(get_bot_service),
):
    try:
        await service.create_bot(payload.to_legacy_config())
        return ok(message="新增平台配置成功~")
    except ValueError as exc:
        return _compat_error(str(exc))


@router.post("/config/platform/update")
async def update_legacy_platform(
    request: Request,
    _auth: AuthContext = Depends(require_config_scope),
    service: BotConfigService = Depends(get_bot_service),
):
    body = await _json_or_empty(request)
    bot_id = body.get("id")
    config = body.get("config")
    if not bot_id or not isinstance(config, dict):
        return _compat_error("参数错误")
    try:
        await service.update_bot(
            str(bot_id),
            BotConfigRequest(config=config).to_legacy_config(fallback_id=str(bot_id)),
        )
        return ok(message="更新平台配置成功~")
    except ValueError as exc:
        return _compat_error(str(exc))


@router.post("/config/platform/delete")
async def delete_legacy_platform(
    request: Request,
    _auth: AuthContext = Depends(require_config_scope),
    service: BotConfigService = Depends(get_bot_service),
):
    body = await _json_or_empty(request)
    bot_id = body.get("id")
    if not bot_id:
        return _compat_error("缺少参数 id")
    try:
        await service.delete_bot(str(bot_id))
        return ok(message="删除平台配置成功~")
    except ValueError as exc:
        return _compat_error(str(exc))


@router.get("/config/provider/template")
async def get_legacy_provider_template(
    _auth: AuthContext = Depends(require_config_scope),
    service: ProviderConfigService = Depends(get_provider_service),
):
    return ok(service.get_provider_schema())


@router.get("/config/provider/list")
async def list_legacy_providers(
    provider_type: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_config_scope),
    service: ProviderConfigService = Depends(get_provider_service),
):
    if not provider_type:
        return _compat_error("缺少参数 provider_type")
    providers = []
    seen_ids = set()
    for item in provider_type.split(","):
        for provider in service.list_providers(capability=item)["providers"]:
            provider_id = provider.get("id")
            if provider_id in seen_ids:
                continue
            seen_ids.add(provider_id)
            providers.append(provider)
    return ok(providers)


@router.post("/config/provider/new")
async def create_legacy_provider(
    payload: ProviderConfigRequest,
    _auth: AuthContext = Depends(require_config_scope),
    service: ProviderConfigService = Depends(get_provider_service),
):
    try:
        await service.create_provider(payload.to_legacy_config())
        return ok(message="新增服务提供商配置成功")
    except ValueError as exc:
        return _compat_error(str(exc))


@router.post("/config/provider/update")
async def update_legacy_provider(
    request: Request,
    _auth: AuthContext = Depends(require_config_scope),
    service: ProviderConfigService = Depends(get_provider_service),
):
    body = await _json_or_empty(request)
    provider_id = body.get("id")
    config = body.get("config")
    if not provider_id or not isinstance(config, dict):
        return _compat_error("参数错误")
    try:
        await service.update_provider(
            str(provider_id),
            ProviderConfigRequest(config=config).to_legacy_config(
                fallback_id=str(provider_id),
            ),
        )
        return ok(message="更新成功，已经实时生效~")
    except ValueError as exc:
        return _compat_error(str(exc))


@router.post("/config/provider/delete")
async def delete_legacy_provider(
    request: Request,
    _auth: AuthContext = Depends(require_config_scope),
    service: ProviderConfigService = Depends(get_provider_service),
):
    body = await _json_or_empty(request)
    provider_id = body.get("id")
    if not provider_id:
        return _compat_error("缺少参数 id")
    try:
        await service.delete_provider(str(provider_id))
        return ok(message="删除成功，已经实时生效。")
    except ValueError as exc:
        return _compat_error(str(exc))


@router.get("/config/provider/check_one")
async def check_legacy_provider(
    id: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_config_scope),
    service: ProviderConfigService = Depends(get_provider_service),
):
    if not id:
        return _compat_error("Missing provider_id parameter")
    try:
        return ok(await service.test_provider(id))
    except ValueError as exc:
        return _compat_error(str(exc))


@router.get("/config/provider_sources/models")
async def list_legacy_provider_source_models(
    source_id: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_config_scope),
    service: ProviderConfigService = Depends(get_provider_service),
):
    if not source_id:
        return _compat_error("缺少参数 source_id")
    try:
        data = await service.list_provider_source_models(source_id)
        data.pop("provider_source_id", None)
        return ok(data)
    except ValueError as exc:
        return _compat_error(str(exc))


@router.post("/config/provider_sources/update")
async def update_legacy_provider_source(
    request: Request,
    _auth: AuthContext = Depends(require_config_scope),
    service: ProviderConfigService = Depends(get_provider_service),
):
    body = await _json_or_empty(request)
    source_id = body.get("original_id")
    config = body.get("config") or body
    if not source_id:
        return _compat_error("缺少 original_id")
    if not isinstance(config, dict):
        return _compat_error("缺少或错误的配置数据")
    try:
        await service.upsert_provider_source(
            str(source_id),
            ProviderSourceRequest(config=config).to_legacy_config(
                fallback_id=str(source_id),
            ),
        )
        return ok(message="更新 provider source 成功")
    except ValueError as exc:
        return _compat_error(str(exc))


@router.post("/config/provider_sources/delete")
async def delete_legacy_provider_source(
    request: Request,
    _auth: AuthContext = Depends(require_config_scope),
    service: ProviderConfigService = Depends(get_provider_service),
):
    body = await _json_or_empty(request)
    source_id = body.get("id")
    if not source_id:
        return _compat_error("缺少 provider_source_id")
    try:
        await service.delete_provider_source(str(source_id))
        return ok(message="删除 provider source 成功")
    except ValueError as exc:
        return _compat_error(str(exc))
