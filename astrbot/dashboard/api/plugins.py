from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import PlainTextResponse, Response

from astrbot.api.web import PluginRequest, bind_request_context
from astrbot.core import logger
from astrbot.dashboard.asgi_runtime import (
    DashboardRequestState,
    call_request_view,
)
from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.responses import ok
from astrbot.dashboard.schemas import (
    EnabledPatch,
    PluginByIdRequest,
    PluginConfigFileDeleteRequest,
    PluginConfigPayload,
    PluginConfigUpdateRequest,
    PluginEnabledRequest,
    PluginInstallRequest,
    PluginSourceRequest,
    PluginUninstallRequest,
    PluginUpdateRequest,
    PluginVersionSupportRequest,
)
from astrbot.dashboard.services.config_service import (
    ConfigDisplayService,
    ConfigFileService,
)
from astrbot.dashboard.services.plugin_page_service import (
    PluginPageContentPayload,
    PluginPageService,
    PluginPageServiceError,
)
from astrbot.dashboard.services.plugin_service import (
    PLUGIN_OPERATION_FAILED_MESSAGE,
    PluginService,
    PluginServiceError,
    PluginServiceWarning,
)

from .auth import AuthContext, require_dashboard_user, require_scope
from .multipart import multipart_parts

router = APIRouter(tags=["Plugins"])
legacy_router = APIRouter(tags=["Dashboard Plugins"], include_in_schema=False)


async def require_plugin_scope(request: Request) -> AuthContext:
    return await require_scope(request, "plugin")


def get_service(request: Request) -> PluginService:
    return request.app.state.services.plugins


def get_page_service(request: Request) -> PluginPageService:
    return request.app.state.services.plugin_pages


def get_config_display_service(request: Request) -> ConfigDisplayService:
    return request.app.state.services.config_display


def get_config_file_service(request: Request) -> ConfigFileService:
    return request.app.state.services.config_files


async def _json_or_empty(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _required_text(value: object, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"Missing key: {name}")
    return text


def _plugin_id_from_body(body: dict[str, Any]) -> str:
    return _required_text(body.get("plugin_id"), "plugin_id")


def _model_dict(payload) -> dict[str, Any]:
    if payload is None:
        return {}
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_none=True)
    return payload if isinstance(payload, dict) else {}


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


async def _run_json(
    request: Request,
    operation: Callable[[dict[str, Any]], Any],
    *,
    log_label: str | None = None,
):
    body = await _json_or_empty(request)
    return await _run_service(lambda: operation(body), log_label=log_label)


def _normalize_plugin_api_route(route: str) -> str:
    route = route.strip()
    if not route.startswith("/"):
        route = f"/{route}"
    return route


def _plugin_api_route_pattern(route: str) -> str:
    normalized = _normalize_plugin_api_route(route)
    chunks = []
    pos = 0
    for match in re.finditer(r"<(?:(path):)?([A-Za-z_][A-Za-z0-9_]*)>", normalized):
        chunks.append(re.escape(normalized[pos : match.start()]))
        name = match.group(2)
        chunks.append(f"(?P<{name}>.*)" if match.group(1) else f"(?P<{name}>[^/]+)")
        pos = match.end()
    chunks.append(re.escape(normalized[pos:]))
    return "".join(chunks)


def _match_registered_web_api(registered_web_apis, subpath: str, method: str):
    request_path = f"/{subpath.lstrip('/')}"
    request_method = method.upper()

    for route, view_handler, methods, _ in registered_web_apis:
        allowed_methods = [item.upper() for item in methods]
        if request_method not in allowed_methods:
            continue

        pattern = _plugin_api_route_pattern(route)
        matched = re.fullmatch(pattern, request_path)
        if matched:
            return view_handler, matched.groupdict()
    return None


def _plugin_extension_legacy_path(plugin_path: str, request: Request) -> str:
    encoded_path = quote(plugin_path.lstrip("/"), safe="/:@!$&'()*+,;=-._~")
    path = f"/api/plug/{encoded_path}"
    if request.url.query:
        return f"{path}?{request.url.query}"
    return path


async def _call_plugin_extension(
    plugin_path: str,
    request: Request,
    username: str,
):
    registered_web_apis = (
        request.app.state.core_lifecycle.star_context.registered_web_apis
    )
    matched_api = _match_registered_web_api(
        registered_web_apis,
        plugin_path,
        request.method,
    )
    if not matched_api:
        return {"status": "error", "message": "未找到该路由", "data": {}}

    view_handler, path_values = matched_api
    plugin_name = plugin_path.strip("/").split("/", 1)[0].strip() or None
    plugin_request = PluginRequest(
        request,
        path_params=path_values,
        plugin_name=plugin_name,
        username=username,
    )
    app_adapter = getattr(request.app.state, "dashboard_app_adapter", None)
    if app_adapter is None:
        with bind_request_context(plugin_request):
            return await run_maybe_async(lambda: view_handler(**path_values))

    g_obj = DashboardRequestState()
    g_obj.username = username
    with bind_request_context(plugin_request):
        return await call_request_view(
            request,
            app_adapter,
            view_handler,
            path_values,
            g_obj=g_obj,
            quart_compat_path=_plugin_extension_legacy_path(plugin_path, request),
        )


def _get_request_locale(request: Request, default: str = "zh-CN") -> str:
    raw_locale = request.headers.get("Accept-Language", "").strip()
    locale = raw_locale.split(",", 1)[0].split(";", 1)[0].strip()
    if not locale or len(locale) > 32:
        return default
    return locale


def _get_request_theme(request: Request) -> str | None:
    theme = request.query_params.get("theme", "").strip()
    return theme if theme in ("dark", "light") else None


def _plugin_page_error_response(status_code: int, message: str):
    return PlainTextResponse(
        message,
        status_code=status_code,
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
        },
    )


def _plugin_page_payload_response(payload: PluginPageContentPayload):
    return Response(
        content=payload.content,
        media_type=payload.content_type,
        headers=PluginPageService.build_security_headers(),
    )


async def _serve_plugin_page_content(
    *,
    request: Request,
    page_service: PluginPageService,
    username: str | None,
    plugin_id: str,
    page_name: str,
    asset_path: str,
):
    try:
        payload = await page_service.serve_page_content(
            plugin_name=plugin_id,
            page_name=page_name,
            asset_path=asset_path,
            asset_token=request.query_params.get("asset_token", "").strip(),
            username=username,
            locale=_get_request_locale(request),
            theme=_get_request_theme(request),
        )
    except PluginPageServiceError as exc:
        return _plugin_page_error_response(exc.status_code, exc.public_message)
    return _plugin_page_payload_response(payload)


async def _serve_plugin_page_bridge_sdk(
    *,
    request: Request,
    page_service: PluginPageService,
):
    try:
        payload = await page_service.serve_bridge_sdk(
            asset_token=request.query_params.get("asset_token", "").strip(),
            locale=_get_request_locale(request),
            theme=_get_request_theme(request),
        )
    except PluginPageServiceError as exc:
        return _plugin_page_error_response(exc.status_code, exc.public_message)
    return _plugin_page_payload_response(payload)


async def _get_plugin_page_entry_config(
    *,
    request: Request,
    page_service: PluginPageService,
    username: str | None,
    plugin_id: str | None,
    page_name: str | None,
):
    try:
        return ok(
            await page_service.get_plugin_page_entry_config(
                plugin_name=plugin_id,
                page_name=page_name,
                username=username,
                locale=_get_request_locale(request),
            )
        )
    except PluginPageServiceError as exc:
        return {"status": "error", "message": exc.public_message, "data": {}}


async def _list_plugins(
    *,
    request: Request,
    service: PluginService,
    page_service: PluginPageService,
):
    return await _run_service(
        service.list_plugins_from_dashboard_query(
            plugin_name=request.query_params.get("name")
            or request.query_params.get("plugin_id"),
            logo_token_resolver=service.get_plugin_logo_token,
            installed_at_resolver=service.get_plugin_installed_at,
            discover_pages=page_service.discover_plugin_pages,
        ),
        log_label="/api/plugin/get",
    )


async def _get_plugin_detail(
    *,
    plugin_id: str | None,
    service: PluginService,
    page_service: PluginPageService,
):
    return await _run_service(
        service.get_plugin_detail(
            plugin_name=plugin_id,
            logo_token_resolver=service.get_plugin_logo_token,
            installed_at_resolver=service.get_plugin_installed_at,
            serialize_pages=page_service.serialize_plugin_pages,
        ),
        log_label="/api/plugin/detail",
    )


async def _install_plugin_upload(
    request: Request,
    service: PluginService,
    *,
    log_label: str,
):
    async def operation():
        form, files = await multipart_parts(request)
        upload_file = files.get("file")
        if upload_file is None:
            raise PluginServiceError("缺少插件文件")
        return await service.install_plugin_upload_from_dashboard_form(
            upload_file=upload_file,
            ignore_version_check=form.get("ignore_version_check", "false"),
        )

    return await _run_service(operation, log_label=log_label)


@router.get("/plugins/extensions/{plugin_path:path}")
async def get_plugin_extension_route(
    plugin_path: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
):
    return await _call_plugin_extension(plugin_path, request, auth.username)


@router.post("/plugins/extensions/{plugin_path:path}")
async def post_plugin_extension_route(
    plugin_path: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
):
    return await _call_plugin_extension(plugin_path, request, auth.username)


@router.put("/plugins/extensions/{plugin_path:path}")
async def put_plugin_extension_route(
    plugin_path: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
):
    return await _call_plugin_extension(plugin_path, request, auth.username)


@router.patch("/plugins/extensions/{plugin_path:path}")
async def patch_plugin_extension_route(
    plugin_path: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
):
    return await _call_plugin_extension(plugin_path, request, auth.username)


@router.delete("/plugins/extensions/{plugin_path:path}")
async def delete_plugin_extension_route(
    plugin_path: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
):
    return await _call_plugin_extension(plugin_path, request, auth.username)


@router.get("/plugins/failed")
async def list_failed_plugins(
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(service.get_failed_plugins)


@router.post("/plugins/update")
async def update_plugins(
    payload: PluginUpdateRequest,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    body = _model_dict(payload)
    if body.get("plugin_id"):
        plugin_id = _plugin_id_from_body(body)
        return await _run_service(
            service.update_plugin(
                {
                    "name": plugin_id,
                    **{key: value for key, value in body.items() if key != "plugin_id"},
                }
            ),
            log_label="/api/plugin/update",
        )
    return await _run_service(
        service.update_all_plugins(
            {
                **body,
                "names": body.get("names") or body.get("plugin_ids") or [],
            }
        ),
        log_label="/api/plugin/update-all",
    )


async def _check_plugin_version_support_payload(
    payload: dict[str, Any],
    service: PluginService,
):
    return await _run_service(
        lambda: service.check_plugin_version_support(payload),
        log_label="/api/plugin/version-support/check",
    )


async def _check_plugin_version_support_request(
    request: Request,
    service: PluginService,
):
    return await _check_plugin_version_support_payload(
        await _json_or_empty(request),
        service,
    )


@router.post("/plugins/version-support/check")
async def check_plugin_version_support(
    payload: PluginVersionSupportRequest,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _check_plugin_version_support_payload(_model_dict(payload), service)


@router.post("/plugins/install/github")
async def install_plugin_from_github(
    payload: PluginInstallRequest,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    body = _model_dict(payload)
    repository = str(body.get("repository") or body.get("url") or "").strip()
    if repository and not repository.startswith(("http://", "https://")):
        repository = f"https://github.com/{repository}"
    install_payload = {
        "url": repository,
        "proxy": body.get("proxy"),
        "ignore_version_check": body.get("ignore_version_check", False),
    }
    if body.get("download_url"):
        install_payload["download_url"] = body["download_url"]
    return await _run_service(
        service.install_plugin(install_payload),
        log_label="/api/plugin/install",
    )


@router.post("/plugins/install/url")
async def install_plugin_from_url(
    payload: PluginInstallRequest | None = Body(default=None),
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    body = _model_dict(payload)
    url = str(body.get("url") or body.get("repository") or "").strip()
    download_url = str(body.get("download_url") or url).strip()
    return await _run_service(
        service.install_plugin(
            {
                "url": url or download_url,
                "download_url": download_url,
                "proxy": body.get("proxy"),
                "ignore_version_check": body.get("ignore_version_check", False),
            }
        ),
        log_label="/api/plugin/install",
    )


@router.post("/plugins/install/upload")
async def install_plugin_from_upload(
    request: Request,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _install_plugin_upload(
        request,
        service,
        log_label="/api/plugin/install-upload",
    )


@router.get("/plugins/market")
async def list_plugin_market(
    request: Request,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        service.get_online_plugins_from_dashboard_query(
            custom_registry=request.query_params.get("custom_registry"),
            force_refresh=request.query_params.get("force_refresh", "false"),
        ),
        log_label="/api/plugin/market_list",
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


@router.delete("/plugin-sources/by-id")
async def delete_plugin_source_by_id(
    source_id: str = Query(...),
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return ok(
        {"sources": await service.delete_custom_source(source_id)},
        message="保存成功",
    )


@router.delete("/plugin-sources/{source_id}")
async def delete_plugin_source(
    source_id: str,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return ok(
        {"sources": await service.delete_custom_source(source_id)},
        message="保存成功",
    )


@router.get("/plugins/page-bridge-sdk.js")
async def get_plugin_page_bridge_sdk(
    request: Request,
    _auth: AuthContext = Depends(require_plugin_scope),
    page_service: PluginPageService = Depends(get_page_service),
):
    return await _serve_plugin_page_bridge_sdk(
        request=request,
        page_service=page_service,
    )


@router.get("/plugins")
async def list_plugins(
    request: Request,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
    page_service: PluginPageService = Depends(get_page_service),
):
    return await _list_plugins(
        request=request,
        service=service,
        page_service=page_service,
    )


@router.get("/plugins/by-id")
async def get_plugin_by_id(
    plugin_id: str = Query(...),
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
    page_service: PluginPageService = Depends(get_page_service),
):
    return await _get_plugin_detail(
        plugin_id=plugin_id,
        service=service,
        page_service=page_service,
    )


@router.delete("/plugins/by-id")
async def uninstall_plugin_by_id(
    payload: PluginUninstallRequest | None = None,
    plugin_id: str = Query(...),
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    body = _model_dict(payload)
    return await _run_service(
        service.uninstall_plugin({"name": plugin_id, **body}),
        log_label="/api/plugin/uninstall",
    )


@router.get("/plugins/config")
async def get_plugin_config_by_id(
    plugin_id: str = Query(...),
    _auth: AuthContext = Depends(require_plugin_scope),
    service: ConfigDisplayService = Depends(get_config_display_service),
):
    return ok({"plugin_name": plugin_id, **await service.get_configs(plugin_id)})


@router.put("/plugins/config")
async def update_plugin_config_by_id(
    payload: PluginConfigUpdateRequest,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: ConfigFileService = Depends(get_config_file_service),
):
    body = _model_dict(payload)
    plugin_id = _plugin_id_from_body(body)
    config = body.get("config")
    config = config if isinstance(config, dict) else {}
    return ok(
        message=await service.save_plugin_configs_from_dashboard_payload(
            config,
            plugin_name=plugin_id,
        )
    )


@router.get("/plugins/config/schema")
async def get_plugin_config_schema_by_id(
    plugin_id: str = Query(...),
    _auth: AuthContext = Depends(require_plugin_scope),
    service: ConfigDisplayService = Depends(get_config_display_service),
):
    return ok({"plugin_name": plugin_id, **await service.get_configs(plugin_id)})


@router.get("/plugins/config-files")
async def list_plugin_config_files_by_id(
    plugin_id: str = Query(...),
    config_key: str = Query(...),
    _auth: AuthContext = Depends(require_plugin_scope),
    service: ConfigFileService = Depends(get_config_file_service),
):
    return ok(
        service.list_config_files(
            scope="plugin",
            name=plugin_id,
            key_path=config_key,
        )
    )


@router.post("/plugins/config-files")
async def upload_plugin_config_files_by_id(
    request: Request,
    plugin_id: str = Query(...),
    config_key: str = Query(...),
    _auth: AuthContext = Depends(require_plugin_scope),
    service: ConfigFileService = Depends(get_config_file_service),
):
    _, files = await multipart_parts(request)
    return ok(
        await service.upload_config_file(
            scope="plugin",
            name=plugin_id,
            key_path=config_key,
            files=files,
        )
    )


@router.delete("/plugins/config-files")
async def delete_plugin_config_file_by_id(
    payload: PluginConfigFileDeleteRequest | None = None,
    plugin_id: str = Query(...),
    _auth: AuthContext = Depends(require_plugin_scope),
    service: ConfigFileService = Depends(get_config_file_service),
):
    return ok(
        message=service.delete_config_file_from_dashboard_payload(
            scope="plugin",
            name=plugin_id,
            payload=_model_dict(payload),
        )
    )


@router.get("/plugins/readme")
async def get_plugin_readme_by_id(
    plugin_id: str = Query(...),
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        lambda: service.get_plugin_readme(plugin_id),
        log_label="/api/plugin/readme",
    )


@router.get("/plugins/changelog")
async def get_plugin_changelog_by_id(
    plugin_id: str = Query(...),
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        lambda: service.get_plugin_changelog(plugin_id),
        log_label="/api/plugin/changelog",
    )


@router.post("/plugins/reload")
async def reload_plugin_by_id(
    payload: PluginByIdRequest,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    plugin_id = _plugin_id_from_body(_model_dict(payload))
    return await _run_service(
        service.reload_plugin({"name": plugin_id}),
        log_label="/api/plugin/reload",
    )


@router.patch("/plugins/enabled")
async def set_plugin_enabled_by_id(
    payload: PluginEnabledRequest,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    body = _model_dict(payload)
    plugin_id = _plugin_id_from_body(body)
    return await _run_service(
        service.set_plugin_enabled(
            {"name": plugin_id}, enabled=bool(body.get("enabled"))
        ),
        log_label="/api/plugin/on" if body.get("enabled") else "/api/plugin/off",
    )


@router.get("/plugins/pages")
async def list_plugin_pages_by_id(
    plugin_id: str = Query(...),
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
    page_service: PluginPageService = Depends(get_page_service),
):
    return await _get_plugin_detail(
        plugin_id=plugin_id,
        service=service,
        page_service=page_service,
    )


@router.get("/plugins/page")
async def get_plugin_page_by_id(
    request: Request,
    plugin_id: str = Query(...),
    page_name: str = Query(...),
    auth: AuthContext = Depends(require_plugin_scope),
    page_service: PluginPageService = Depends(get_page_service),
):
    return await _get_plugin_page_entry_config(
        request=request,
        page_service=page_service,
        username=auth.username,
        plugin_id=plugin_id,
        page_name=page_name,
    )


@router.get("/plugins/page/assets")
async def get_plugin_page_asset_by_id(
    request: Request,
    plugin_id: str = Query(...),
    page_name: str = Query(...),
    asset_path: str = Query(...),
    auth: AuthContext = Depends(require_plugin_scope),
    page_service: PluginPageService = Depends(get_page_service),
):
    return await _serve_plugin_page_content(
        request=request,
        page_service=page_service,
        username=auth.username,
        plugin_id=plugin_id,
        page_name=page_name,
        asset_path=asset_path,
    )


@router.get("/plugins/{plugin_id}")
async def get_plugin(
    plugin_id: str,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
    page_service: PluginPageService = Depends(get_page_service),
):
    return await _get_plugin_detail(
        plugin_id=plugin_id,
        service=service,
        page_service=page_service,
    )


@router.delete("/plugins/{plugin_id}")
async def uninstall_plugin(
    plugin_id: str,
    payload: PluginUninstallRequest | None = None,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    body = _model_dict(payload)
    return await _run_service(
        service.uninstall_plugin({"name": plugin_id, **body}),
        log_label="/api/plugin/uninstall",
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
        log_label="/api/plugin/uninstall-failed",
    )


@router.post("/plugins/failed/{plugin_id}/reload")
async def reload_failed_plugin(
    plugin_id: str,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        service.reload_failed_plugin({"dir_name": plugin_id}),
        log_label="/api/plugin/reload-failed",
    )


@router.get("/plugins/{plugin_id}/config")
async def get_plugin_config(
    plugin_id: str,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: ConfigDisplayService = Depends(get_config_display_service),
):
    return ok({"plugin_name": plugin_id, **await service.get_configs(plugin_id)})


@router.put("/plugins/{plugin_id}/config")
async def update_plugin_config(
    plugin_id: str,
    payload: PluginConfigPayload,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: ConfigFileService = Depends(get_config_file_service),
):
    body = _model_dict(payload)
    config = body.get("config")
    config = config if isinstance(config, dict) else body
    return ok(
        message=await service.save_plugin_configs_from_dashboard_payload(
            config,
            plugin_name=plugin_id,
        )
    )


@router.get("/plugins/{plugin_id}/config/schema")
async def get_plugin_config_schema(
    plugin_id: str,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: ConfigDisplayService = Depends(get_config_display_service),
):
    return ok({"plugin_name": plugin_id, **await service.get_configs(plugin_id)})


@router.get("/plugins/{plugin_id}/config-files/{config_key:path}")
async def list_plugin_config_files(
    plugin_id: str,
    config_key: str,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: ConfigFileService = Depends(get_config_file_service),
):
    return ok(
        service.list_config_files(
            scope="plugin",
            name=plugin_id,
            key_path=config_key,
        )
    )


@router.post("/plugins/{plugin_id}/config-files/{config_key:path}")
async def upload_plugin_config_files(
    plugin_id: str,
    config_key: str,
    request: Request,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: ConfigFileService = Depends(get_config_file_service),
):
    _, files = await multipart_parts(request)
    return ok(
        await service.upload_config_file(
            scope="plugin",
            name=plugin_id,
            key_path=config_key,
            files=files,
        )
    )


@router.delete("/plugins/{plugin_id}/config-files")
async def delete_plugin_config_file(
    plugin_id: str,
    payload: PluginConfigFileDeleteRequest | None = None,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: ConfigFileService = Depends(get_config_file_service),
):
    return ok(
        message=service.delete_config_file_from_dashboard_payload(
            scope="plugin",
            name=plugin_id,
            payload=_model_dict(payload),
        )
    )


@router.get("/plugins/{plugin_id}/readme")
async def get_plugin_readme(
    plugin_id: str,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        lambda: service.get_plugin_readme(plugin_id),
        log_label="/api/plugin/readme",
    )


@router.get("/plugins/{plugin_id}/changelog")
async def get_plugin_changelog(
    plugin_id: str,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        lambda: service.get_plugin_changelog(plugin_id),
        log_label="/api/plugin/changelog",
    )


@router.post("/plugins/{plugin_id}/reload")
async def reload_plugin(
    plugin_id: str,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        service.reload_plugin({"name": plugin_id}),
        log_label="/api/plugin/reload",
    )


@router.patch("/plugins/{plugin_id}/enabled")
async def set_plugin_enabled(
    plugin_id: str,
    payload: EnabledPatch,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        service.set_plugin_enabled({"name": plugin_id}, enabled=payload.enabled),
        log_label="/api/plugin/on" if payload.enabled else "/api/plugin/off",
    )


@router.post("/plugins/{plugin_id}/update")
async def update_plugin(
    plugin_id: str,
    payload: PluginUpdateRequest | None = None,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    body = _model_dict(payload)
    return await _run_service(
        service.update_plugin({"name": plugin_id, **body}),
        log_label="/api/plugin/update",
    )


@router.get("/plugins/{plugin_id}/pages")
async def list_plugin_pages(
    plugin_id: str,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
    page_service: PluginPageService = Depends(get_page_service),
):
    return await _get_plugin_detail(
        plugin_id=plugin_id,
        service=service,
        page_service=page_service,
    )


@router.get("/plugins/{plugin_id}/pages/{page_name}")
async def get_plugin_page(
    plugin_id: str,
    page_name: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    page_service: PluginPageService = Depends(get_page_service),
):
    return await _get_plugin_page_entry_config(
        request=request,
        page_service=page_service,
        username=auth.username,
        plugin_id=plugin_id,
        page_name=page_name,
    )


@router.get("/plugins/{plugin_id}/pages/{page_name}/assets/{asset_path:path}")
async def get_plugin_page_asset(
    plugin_id: str,
    page_name: str,
    asset_path: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    page_service: PluginPageService = Depends(get_page_service),
):
    return await _serve_plugin_page_content(
        request=request,
        page_service=page_service,
        username=auth.username,
        plugin_id=plugin_id,
        page_name=page_name,
        asset_path=asset_path,
    )


@legacy_router.get("/api/plugin/get")
async def dashboard_list_plugins(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PluginService = Depends(get_service),
    page_service: PluginPageService = Depends(get_page_service),
):
    return await _list_plugins(
        request=request,
        service=service,
        page_service=page_service,
    )


@legacy_router.get("/api/plugin/detail")
async def dashboard_get_plugin_detail(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PluginService = Depends(get_service),
    page_service: PluginPageService = Depends(get_page_service),
):
    return await _get_plugin_detail(
        plugin_id=request.query_params.get("name"),
        service=service,
        page_service=page_service,
    )


@legacy_router.post("/api/plugin/check-compat")
async def dashboard_check_plugin_version_support(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PluginService = Depends(get_service),
):
    return await _check_plugin_version_support_request(request, service)


@legacy_router.get("/api/plugin/page/entry")
async def dashboard_get_plugin_page_entry_config(
    request: Request,
    username: str = Depends(require_dashboard_user),
    page_service: PluginPageService = Depends(get_page_service),
):
    return await _get_plugin_page_entry_config(
        request=request,
        page_service=page_service,
        username=username,
        plugin_id=request.query_params.get("name"),
        page_name=request.query_params.get("page"),
    )


@legacy_router.post("/api/plugin/install")
async def dashboard_install_plugin(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PluginService = Depends(get_service),
):
    return await _run_json(
        request,
        service.install_plugin,
        log_label="/api/plugin/install",
    )


@legacy_router.post("/api/plugin/install-upload")
async def dashboard_install_plugin_upload(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PluginService = Depends(get_service),
):
    return await _install_plugin_upload(
        request,
        service,
        log_label="/api/plugin/install-upload",
    )


@legacy_router.post("/api/plugin/update")
async def dashboard_update_plugin(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PluginService = Depends(get_service),
):
    return await _run_json(
        request,
        service.update_plugin,
        log_label="/api/plugin/update",
    )


@legacy_router.post("/api/plugin/update-all")
async def dashboard_update_all_plugins(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PluginService = Depends(get_service),
):
    return await _run_json(
        request,
        service.update_all_plugins,
        log_label="/api/plugin/update-all",
    )


@legacy_router.post("/api/plugin/uninstall")
async def dashboard_uninstall_plugin(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PluginService = Depends(get_service),
):
    return await _run_json(
        request,
        service.uninstall_plugin,
        log_label="/api/plugin/uninstall",
    )


@legacy_router.post("/api/plugin/uninstall-failed")
async def dashboard_uninstall_failed_plugin(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PluginService = Depends(get_service),
):
    return await _run_json(
        request,
        service.uninstall_failed_plugin,
        log_label="/api/plugin/uninstall-failed",
    )


@legacy_router.get("/api/plugin/market_list")
async def dashboard_list_plugin_market(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        service.get_online_plugins_from_dashboard_query(
            custom_registry=request.query_params.get("custom_registry"),
            force_refresh=request.query_params.get("force_refresh", "false"),
        ),
        log_label="/api/plugin/market_list",
    )


@legacy_router.post("/api/plugin/off")
async def dashboard_disable_plugin(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PluginService = Depends(get_service),
):
    return await _run_json(
        request,
        lambda data: service.set_plugin_enabled(data, enabled=False),
        log_label="/api/plugin/off",
    )


@legacy_router.post("/api/plugin/on")
async def dashboard_enable_plugin(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PluginService = Depends(get_service),
):
    return await _run_json(
        request,
        lambda data: service.set_plugin_enabled(data, enabled=True),
        log_label="/api/plugin/on",
    )


@legacy_router.post("/api/plugin/reload-failed")
async def dashboard_reload_failed_plugin(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PluginService = Depends(get_service),
):
    return await _run_json(
        request,
        service.reload_failed_plugin,
        log_label="/api/plugin/reload-failed",
    )


@legacy_router.post("/api/plugin/reload")
async def dashboard_reload_plugin(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PluginService = Depends(get_service),
):
    return await _run_json(
        request,
        service.reload_plugin,
        log_label="/api/plugin/reload",
    )


@legacy_router.get("/api/plugin/readme")
async def dashboard_get_plugin_readme(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        lambda: service.get_plugin_readme(request.query_params.get("name")),
        log_label="/api/plugin/readme",
    )


@legacy_router.get("/api/plugin/changelog")
async def dashboard_get_plugin_changelog(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        lambda: service.get_plugin_changelog(request.query_params.get("name")),
        log_label="/api/plugin/changelog",
    )


@legacy_router.get("/api/plugin/source/get")
async def dashboard_get_custom_source(
    _username: str = Depends(require_dashboard_user),
    service: PluginService = Depends(get_service),
):
    return await _run_service(service.get_custom_sources)


@legacy_router.post("/api/plugin/source/save")
async def dashboard_save_custom_source(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: PluginService = Depends(get_service),
):
    return await _run_json(
        request,
        service.save_custom_sources,
        log_label="/api/plugin/source/save",
    )


@legacy_router.get("/api/plugin/source/get-failed-plugins")
async def dashboard_get_failed_plugins(
    _username: str = Depends(require_dashboard_user),
    service: PluginService = Depends(get_service),
):
    return await _run_service(service.get_failed_plugins)


@legacy_router.get("/api/plugin/page/bridge-sdk.js")
async def dashboard_get_plugin_page_bridge_sdk(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    page_service: PluginPageService = Depends(get_page_service),
):
    return await _serve_plugin_page_bridge_sdk(
        request=request,
        page_service=page_service,
    )


@legacy_router.get("/api/plugin/page/content/{plugin_id}/{page_name}/")
async def dashboard_get_plugin_page_entry(
    plugin_id: str,
    page_name: str,
    request: Request,
    username: str = Depends(require_dashboard_user),
    page_service: PluginPageService = Depends(get_page_service),
):
    return await _serve_plugin_page_content(
        request=request,
        page_service=page_service,
        username=username,
        plugin_id=plugin_id,
        page_name=page_name,
        asset_path="",
    )


@legacy_router.get("/api/plugin/page/content/{plugin_id}/{page_name}/{asset_path:path}")
async def dashboard_get_plugin_page_asset(
    plugin_id: str,
    page_name: str,
    asset_path: str,
    request: Request,
    username: str = Depends(require_dashboard_user),
    page_service: PluginPageService = Depends(get_page_service),
):
    return await _serve_plugin_page_content(
        request=request,
        page_service=page_service,
        username=username,
        plugin_id=plugin_id,
        page_name=page_name,
        asset_path=asset_path,
    )


@legacy_router.api_route("/api/plug/{plugin_path:path}", methods=["GET", "POST"])
async def dashboard_plugin_extension_route(
    plugin_path: str,
    request: Request,
    username: str = Depends(require_dashboard_user),
):
    return await _call_plugin_extension(plugin_path, request, username)
