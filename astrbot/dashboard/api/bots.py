from fastapi import APIRouter, Depends, Query, Request

from astrbot.core.auth.models import Resource
from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import BotActionRequest, BotConfigRequest, EnabledPatch
from astrbot.dashboard.services.config_service import BotConfigService
from astrbot.dashboard.services.platform_service import (
    PlatformService,
    PlatformServiceError,
)

from .auth import (
    AuthContext,
    object_resource,
    require_resource_action,
    require_scope,
)

router = APIRouter(tags=["Bots"])


async def require_bot_scope(request: Request) -> AuthContext:
    auth = await require_scope(request, "bot")
    bot_id = request.path_params.get("bot_id")
    resource = (
        object_resource("bot", bot_id)
        if bot_id
        else Resource.named("bot", "collection")
    )
    action = (
        "platform.read"
        if request.method.upper() in {"GET", "HEAD"}
        else "platform.manage"
    )
    await require_resource_action(
        request,
        auth,
        action=action,
        resource=resource,
    )
    return auth


def get_service(request: Request) -> BotConfigService:
    return request.app.state.services.bots


def get_platform_service(request: Request) -> PlatformService:
    return request.app.state.services.platforms


def _raise_platform_error(exc: PlatformServiceError) -> None:
    raise ApiError(str(exc), status_code=exc.status_code) from exc


@router.get("/bot-types")
async def list_bot_types(
    _auth: AuthContext = Depends(require_bot_scope),
    service: BotConfigService = Depends(get_service),
):
    return ok(service.list_bot_types())


@router.get("/bots")
async def list_bots(
    enabled: bool | None = Query(default=None),
    type_: str | None = Query(default=None, alias="type"),
    _auth: AuthContext = Depends(require_bot_scope),
    service: BotConfigService = Depends(get_service),
):
    return ok(service.list_bots(enabled=enabled, type_=type_))


@router.post("/bots")
async def create_bot(
    payload: BotConfigRequest,
    _auth: AuthContext = Depends(require_bot_scope),
    service: BotConfigService = Depends(get_service),
):
    config = dict(payload.config)
    config.setdefault("enable", True)
    await service.create_bot(config)
    return ok(message="新增平台配置成功~")


@router.get("/bots/stats")
async def list_bot_stats(
    _auth: AuthContext = Depends(require_bot_scope),
    service: BotConfigService = Depends(get_service),
):
    return ok(service.get_bot_stats())


@router.patch("/bots/{bot_id:path}/enabled")
async def set_bot_enabled(
    bot_id: str,
    payload: EnabledPatch,
    _auth: AuthContext = Depends(require_bot_scope),
    service: BotConfigService = Depends(get_service),
):
    await service.set_bot_enabled(bot_id, payload.enabled)
    return ok(message="更新平台配置成功~")


@router.post("/bots/{bot_id:path}/test")
async def test_bot(
    bot_id: str,
    _auth: AuthContext = Depends(require_bot_scope),
):
    return ok({"id": bot_id, "status": "unsupported"})


@router.post("/bots/{bot_id:path}/actions")
async def invoke_bot_action(
    bot_id: str,
    payload: BotActionRequest,
    _auth: AuthContext = Depends(require_bot_scope),
    platform_service: PlatformService = Depends(get_platform_service),
):
    try:
        result = await platform_service.invoke_platform_action(
            bot_id,
            payload.action_name,
            payload.payload,
        )
    except PlatformServiceError as exc:
        _raise_platform_error(exc)
    return ok(result)


@router.get("/bots/{bot_id:path}")
async def get_bot(
    bot_id: str,
    _auth: AuthContext = Depends(require_bot_scope),
    service: BotConfigService = Depends(get_service),
):
    return ok(service.get_bot(bot_id))


@router.put("/bots/{bot_id:path}")
async def update_bot(
    bot_id: str,
    payload: BotConfigRequest,
    _auth: AuthContext = Depends(require_bot_scope),
    service: BotConfigService = Depends(get_service),
):
    config = dict(payload.config)
    if "id" not in config:
        config["id"] = bot_id
    config.setdefault("enable", True)
    await service.update_bot(bot_id, config)
    return ok(message="更新平台配置成功~")


@router.delete("/bots/{bot_id:path}")
async def delete_bot(
    bot_id: str,
    _auth: AuthContext = Depends(require_bot_scope),
    service: BotConfigService = Depends(get_service),
):
    await service.delete_bot(bot_id)
    return ok(message="删除平台配置成功~")
