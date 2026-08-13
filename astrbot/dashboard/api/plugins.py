from typing import Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from astrbot import logger
from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import (
    EnabledPatch,
    PluginBatchUpdateRequest,
    PluginConfigFileDeleteRequest,
    PluginConfigPayload,
    PluginGithubInstallRequest,
    PluginLogLevelPayload,
    PluginSourceBindRequest,
    PluginSourceRequest,
    PluginUninstallRequest,
    PluginUpdateRequest,
    PluginUrlInstallRequest,
)
from astrbot.dashboard.services.config_service import (
    ConfigDisplayService,
    ConfigFileService,
)
from astrbot.dashboard.services.plugin_log_level_service import PluginLogLevelService
from astrbot.dashboard.services.plugin_service import (
    PLUGIN_OPERATION_FAILED_MESSAGE,
    PluginService,
    PluginServiceError,
    PluginServiceWarning,
)

from .auth import AuthContext, require_scope

router = APIRouter(tags=["Plugins"])


async def require_plugin_scope(request: Request) -> AuthContext:
    return await require_scope(request, "plugin")


async def require_plugin_install_scope(request: Request) -> AuthContext:
    return await require_scope(
        request,
        "plugin",
        action_override="extension.plugin_install",
    )


def get_service(request: Request) -> PluginService:
    return request.app.state.services.plugins


def get_config_display_service(request: Request) -> ConfigDisplayService:
    return request.app.state.services.config_display


def get_config_file_service(request: Request) -> ConfigFileService:
    return request.app.state.services.config_files


def get_plugin_log_level_service(request: Request) -> PluginLogLevelService:
    return request.app.state.services.plugin_log_levels


async def require_plugin_id_scope(
    request: Request,
    plugin_id: str,
) -> AuthContext:
    if plugin_id.split("/", 1)[0] == "extensions":
        raise ApiError("Plugin not found", status_code=404)
    return await require_plugin_scope(request)


def _reject_legacy_plugin_query_params(request: Request, *forbidden: str) -> None:
    legacy_fields = [key for key in forbidden if key in request.query_params]
    if legacy_fields:
        fields = ", ".join(sorted(legacy_fields))
        raise ApiError(f"Legacy plugin query parameters are not supported: {fields}")


def _model_dict(payload) -> dict[str, Any]:
    if payload is None:
        return {}
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_none=True)
    return payload if isinstance(payload, dict) else {}


def _normalize_github_repository(repository: str) -> str:
    normalized = repository.strip()
    if normalized and not normalized.startswith(("http://", "https://")):
        return f"https://github.com/{normalized}"
    return normalized


def _service_ok(result):
    if isinstance(result, tuple):
        data, message = result
        return ok(data, message)
    return ok(result)


async def _run_service(operation, *, log_label: str | None = None):
    try:
        result = await run_maybe_async(operation)
        return _service_ok(result)
    except PluginServiceWarning as exc:
        return {
            "status": "warning",
            "message": exc.public_message,
            "data": exc.data,
        }
    except PluginServiceError as exc:
        return {"status": "error", "message": exc.public_message, "data": {}}
    except Exception:
        if log_label:
            logger.error("%s failed", log_label, exc_info=True)
        else:
            logger.error("Plugin service operation failed", exc_info=True)
        return {
            "status": "error",
            "message": PLUGIN_OPERATION_FAILED_MESSAGE,
            "data": {},
        }


@router.get("/plugins/failed")
async def list_failed_plugins(
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(service.get_failed_plugins)


@router.post("/plugins/update")
async def update_plugins(
    payload: PluginBatchUpdateRequest,
    _auth: AuthContext = Depends(require_plugin_install_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        service.update_all_plugins(payload.model_dump(exclude_none=True)),
        log_label="/api/v1/plugins/update-all",
    )


@router.post("/plugins/install/github")
async def install_plugin_from_github(
    payload: PluginGithubInstallRequest,
    _auth: AuthContext = Depends(require_plugin_install_scope),
    service: PluginService = Depends(get_service),
):
    body = payload.model_dump(exclude_none=True)
    repository = _normalize_github_repository(payload.repository)
    install_payload = {
        "url": repository,
        "proxy": body.get("proxy"),
        "ignore_version_check": body.get("ignore_version_check", False),
        **{
            key: body[key]
            for key in (
                "install_method",
                "registry_url",
                "market_plugin_id",
            )
            if key in body
        },
    }
    if payload.download_url:
        install_payload["download_url"] = body["download_url"]
    return await _run_service(
        service.install_plugin(install_payload),
        log_label="/api/v1/plugins/install/github",
    )


@router.post("/plugins/install/url")
async def install_plugin_from_url(
    payload: PluginUrlInstallRequest,
    _auth: AuthContext = Depends(require_plugin_install_scope),
    service: PluginService = Depends(get_service),
):
    body = payload.model_dump(exclude_none=True)
    url = payload.url.strip()
    download_url = str(payload.download_url or url).strip()
    return await _run_service(
        service.install_plugin(
            {
                "url": url or download_url,
                "download_url": download_url,
                "proxy": body.get("proxy"),
                "ignore_version_check": body.get("ignore_version_check", False),
                **{
                    key: body[key]
                    for key in (
                        "install_method",
                        "registry_url",
                        "market_plugin_id",
                    )
                    if key in body
                },
            }
        ),
        log_label="/api/v1/plugins/install/url",
    )


@router.post("/plugins/install/upload")
async def install_plugin_from_upload(
    file: UploadFile = File(...),
    ignore_version_check: bool = Form(False),
    _auth: AuthContext = Depends(require_plugin_install_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        service.install_plugin_upload(
            upload_file=file,
            ignore_version_check=ignore_version_check,
        ),
        log_label="/api/v1/plugins/install/upload",
    )


@router.get("/plugins/market")
async def list_plugin_market(
    request: Request,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    force_refresh = str(request.query_params.get("force_refresh") or "").strip().lower()
    return await _run_service(
        service.get_online_plugins(
            custom_registry=request.query_params.get("custom_registry"),
            force_refresh=force_refresh in {"1", "true", "yes", "on"},
        ),
        log_label="/api/v1/plugins/market",
    )


@router.get("/plugins/market/categories")
async def list_plugin_market_categories(
    _auth: AuthContext = Depends(require_plugin_scope),
):
    return ok({"categories": []})


@router.get("/plugin-sources")
async def list_plugin_sources(
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return ok({"sources": await service.get_custom_sources()})


@router.post("/plugin-sources")
async def create_plugin_source(
    payload: PluginSourceRequest,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return ok(
        {"sources": await service.create_custom_source(_model_dict(payload))},
        message="保存成功",
    )


@router.put("/plugin-sources")
async def replace_plugin_sources(
    payload: PluginSourceRequest,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return ok(
        {"sources": await service.replace_custom_sources(_model_dict(payload))},
        message="保存成功",
    )


@router.delete("/plugin-sources/{source_id:path}")
async def delete_plugin_source(
    source_id: str,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return ok(
        {"sources": await service.delete_custom_source(source_id)},
        message="保存成功",
    )


@router.get("/plugins")
async def list_plugins(
    request: Request,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    _reject_legacy_plugin_query_params(request, "plugin_id")
    return await _run_service(
        service.list_plugins(
            plugin_name=request.query_params.get("name"),
            logo_token_resolver=service.get_plugin_logo_token,
            installed_at_resolver=service.get_plugin_installed_at,
        ),
        log_label="/api/v1/plugins",
    )


@router.delete("/plugins/failed/{plugin_id}")
async def uninstall_failed_plugin(
    plugin_id: str,
    payload: PluginUninstallRequest | None = None,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    body = _model_dict(payload)
    return await _run_service(
        service.uninstall_failed_plugin({"dir_name": plugin_id, **body}),
        log_label="/api/v1/plugins/failed/{plugin_id}",
    )


@router.post("/plugins/failed/{plugin_id}/reload")
async def reload_failed_plugin(
    plugin_id: str,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        service.reload_failed_plugin({"dir_name": plugin_id}),
        log_label="/api/v1/plugins/failed/{plugin_id}/reload",
    )


@router.get("/plugins/{plugin_id:path}/config")
async def get_plugin_config(
    plugin_id: str,
    _auth: AuthContext = Depends(require_plugin_id_scope),
    service: ConfigDisplayService = Depends(get_config_display_service),
    log_levels: PluginLogLevelService = Depends(get_plugin_log_level_service),
):
    return ok(
        {
            "plugin_name": plugin_id,
            "log_level": log_levels.get_plugin_log_level(plugin_id),
            **await service.get_configs(plugin_id),
        }
    )


@router.put("/plugins/{plugin_id:path}/log-level")
async def update_plugin_log_level(
    plugin_id: str,
    payload: PluginLogLevelPayload,
    _auth: AuthContext = Depends(require_plugin_id_scope),
    service: PluginLogLevelService = Depends(get_plugin_log_level_service),
):
    try:
        level = service.set_plugin_log_level(plugin_id, payload.level)
    except KeyError as exc:
        raise ApiError("Plugin not found", status_code=404) from exc
    except ValueError as exc:
        raise ApiError(str(exc)) from exc
    return ok(
        {"log_level": level},
        message=f"Plugin {plugin_id} log level updated.",
    )


@router.put("/plugins/{plugin_id:path}/config")
async def update_plugin_config(
    plugin_id: str,
    payload: PluginConfigPayload,
    _auth: AuthContext = Depends(require_plugin_id_scope),
    service: ConfigFileService = Depends(get_config_file_service),
):
    body = _model_dict(payload)
    config = body.get("config")
    config = config if isinstance(config, dict) else body
    await service.save_plugin_configs(config, plugin_id)
    return ok(message=f"保存插件 {plugin_id} 成功~ 机器人正在热重载插件。")


@router.get("/plugins/{plugin_id:path}/config/schema")
async def get_plugin_config_schema(
    plugin_id: str,
    _auth: AuthContext = Depends(require_plugin_id_scope),
    service: ConfigDisplayService = Depends(get_config_display_service),
):
    return ok({"plugin_name": plugin_id, **await service.get_configs(plugin_id)})


@router.get("/plugins/{plugin_id:path}/config-files/{config_key:path}")
async def list_plugin_config_files(
    plugin_id: str,
    config_key: str,
    _auth: AuthContext = Depends(require_plugin_id_scope),
    service: ConfigFileService = Depends(get_config_file_service),
):
    return ok(
        service.list_config_files(
            scope="plugin",
            name=plugin_id,
            key_path=config_key,
        )
    )


@router.post("/plugins/{plugin_id:path}/config-files/{config_key:path}")
async def upload_plugin_config_files(
    plugin_id: str,
    config_key: str,
    request: Request,
    _auth: AuthContext = Depends(require_plugin_id_scope),
    service: ConfigFileService = Depends(get_config_file_service),
):
    form = await request.form()
    files = [value for _, value in form.multi_items() if isinstance(value, UploadFile)]
    return ok(
        await service.upload_config_file(
            scope="plugin",
            name=plugin_id,
            key_path=config_key,
            files=files,
        )
    )


@router.delete("/plugins/{plugin_id:path}/config-files")
async def delete_plugin_config_file(
    plugin_id: str,
    payload: PluginConfigFileDeleteRequest | None = None,
    _auth: AuthContext = Depends(require_plugin_id_scope),
    service: ConfigFileService = Depends(get_config_file_service),
):
    body = _model_dict(payload)
    service.delete_config_file(
        scope="plugin",
        name=plugin_id,
        rel_path=body.get("path"),
    )
    return ok(message="Deleted")


@router.get("/plugins/{plugin_id:path}/readme")
async def get_plugin_readme(
    plugin_id: str,
    _auth: AuthContext = Depends(require_plugin_id_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        lambda: service.get_plugin_readme(plugin_id),
        log_label="/api/v1/plugins/{plugin_id}/readme",
    )


@router.get("/plugins/{plugin_id:path}/changelog")
async def get_plugin_changelog(
    plugin_id: str,
    _auth: AuthContext = Depends(require_plugin_id_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        lambda: service.get_plugin_changelog(plugin_id),
        log_label="/api/v1/plugins/{plugin_id}/changelog",
    )


@router.post("/plugins/{plugin_id:path}/reload")
async def reload_plugin(
    plugin_id: str,
    _auth: AuthContext = Depends(require_plugin_id_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        service.reload_plugin({"name": plugin_id}),
        log_label="/api/v1/plugins/{plugin_id}/reload",
    )


@router.post("/plugins/{plugin_id:path}/source")
async def bind_plugin_source(
    plugin_id: str,
    payload: PluginSourceBindRequest,
    _auth: AuthContext = Depends(require_plugin_id_scope),
    service: PluginService = Depends(get_service),
):
    body = _model_dict(payload)
    return await _run_service(
        service.bind_plugin_market_source({"name": plugin_id, **body}),
        log_label="/api/plugin/source",
    )


@router.patch("/plugins/{plugin_id:path}/enabled")
async def set_plugin_enabled(
    plugin_id: str,
    payload: EnabledPatch,
    _auth: AuthContext = Depends(require_plugin_id_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        service.set_plugin_enabled({"name": plugin_id}, enabled=payload.enabled),
        log_label="/api/v1/plugins/{plugin_id}/enabled:on"
        if payload.enabled
        else "/api/v1/plugins/{plugin_id}/enabled:off",
    )


@router.post("/plugins/{plugin_id:path}/update")
async def update_plugin(
    plugin_id: str,
    payload: PluginUpdateRequest | None = None,
    _auth: AuthContext = Depends(require_plugin_install_scope),
    service: PluginService = Depends(get_service),
):
    body = _model_dict(payload)
    return await _run_service(
        service.update_plugin({"name": plugin_id, **body}),
        log_label="/api/v1/plugins/{plugin_id}/update",
    )


@router.get("/plugins/{plugin_id:path}")
async def get_plugin(
    plugin_id: str,
    _auth: AuthContext = Depends(require_plugin_id_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        service.get_plugin_detail(
            plugin_name=plugin_id,
            logo_token_resolver=service.get_plugin_logo_token,
            installed_at_resolver=service.get_plugin_installed_at,
        ),
        log_label="/api/v1/plugins/{plugin_id}",
    )


@router.delete("/plugins/{plugin_id:path}")
async def uninstall_plugin(
    plugin_id: str,
    payload: PluginUninstallRequest | None = None,
    _auth: AuthContext = Depends(require_plugin_id_scope),
    service: PluginService = Depends(get_service),
):
    body = _model_dict(payload)
    return await _run_service(
        service.uninstall_plugin({"name": plugin_id, **body}),
        log_label="/api/v1/plugins/{plugin_id}",
    )
