from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from astrbot.dashboard.services.plugin_service import PluginService, PluginServiceError
from astrbot.dashboard.services.route_bridge_service import DashboardRouteBridgeService

from ..auth import AuthContext, require_scope
from ..responses import ApiError, ok

router = APIRouter(tags=["Plugins"])


async def require_plugin_scope(request: Request) -> AuthContext:
    return await require_scope(request, "plugin")


def get_bridge(request: Request) -> DashboardRouteBridgeService:
    return request.app.state.services.route_bridge


def get_service(request: Request) -> PluginService:
    return request.app.state.services.plugins


async def _proxy_plugin_extension(
    plugin_path: str,
    request: Request,
    auth: AuthContext,
    bridge: DashboardRouteBridgeService,
):
    return await bridge.forward(
        request,
        auth,
        method=request.method,
        target_path=f"/api/plug/{plugin_path.lstrip('/')}",
    )


@router.get("/plugins/extensions/{plugin_path:path}")
async def get_plugin_extension_route(
    plugin_path: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await _proxy_plugin_extension(plugin_path, request, auth, bridge)


@router.post("/plugins/extensions/{plugin_path:path}")
async def post_plugin_extension_route(
    plugin_path: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await _proxy_plugin_extension(plugin_path, request, auth, bridge)


@router.put("/plugins/extensions/{plugin_path:path}")
async def put_plugin_extension_route(
    plugin_path: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await _proxy_plugin_extension(plugin_path, request, auth, bridge)


@router.patch("/plugins/extensions/{plugin_path:path}")
async def patch_plugin_extension_route(
    plugin_path: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await _proxy_plugin_extension(plugin_path, request, auth, bridge)


@router.delete("/plugins/extensions/{plugin_path:path}")
async def delete_plugin_extension_route(
    plugin_path: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await _proxy_plugin_extension(plugin_path, request, auth, bridge)


async def _json_or_empty(request: Request) -> dict:
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


def _plugin_id_from_body(body: dict) -> str:
    return _required_text(body.get("plugin_id"), "plugin_id")


@router.get("/plugins/failed")
async def list_failed_plugins(
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/plugin/source/get-failed-plugins",
    )


@router.post("/plugins/update")
async def update_plugins(
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    if body.get("plugin_id"):
        plugin_id = _plugin_id_from_body(body)
        return await bridge.forward(
            request,
            auth,
            method="POST",
            target_path="/api/plugin/update",
            json_body={
                "name": plugin_id,
                **{key: value for key, value in body.items() if key != "plugin_id"},
            },
        )
    legacy_body = {
        **body,
        "names": body.get("names") or body.get("plugin_ids") or [],
    }
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/plugin/update-all",
        json_body=legacy_body,
    )


@router.post("/plugins/compatibility/check")
async def check_plugin_compatibility(
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/plugin/check-compat",
    )


@router.post("/plugins/install/github")
async def install_plugin_from_github(
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    repository = str(body.get("repository") or body.get("url") or "").strip()
    if repository and not repository.startswith(("http://", "https://")):
        repository = f"https://github.com/{repository}"
    legacy_body = {
        "url": repository,
        "proxy": body.get("proxy"),
        "ignore_version_check": body.get("ignore_version_check", False),
    }
    if body.get("download_url"):
        legacy_body["download_url"] = body["download_url"]
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/plugin/install",
        json_body=legacy_body,
    )


@router.post("/plugins/install/url")
async def install_plugin_from_url(
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    url = str(body.get("url") or "").strip()
    legacy_body = {
        "url": body.get("repository") or url,
        "download_url": url,
        "proxy": body.get("proxy"),
        "ignore_version_check": body.get("ignore_version_check", False),
    }
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/plugin/install",
        json_body=legacy_body,
    )


@router.post("/plugins/install/upload")
async def install_plugin_from_upload(
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/plugin/install-upload",
    )


@router.get("/plugins/market")
async def list_plugin_market(
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/plugin/market_list",
    )


@router.get("/plugins/market/categories")
async def list_plugin_market_categories(
    _request: Request,
    _auth: AuthContext = Depends(require_plugin_scope),
):
    return ok({"categories": []})


@router.get("/plugin-sources")
async def list_plugin_sources(
    _request: Request,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return ok({"sources": await service.get_custom_sources()})


@router.post("/plugin-sources")
async def create_plugin_source(
    request: Request,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    body = await _json_or_empty(request)
    try:
        sources = await service.create_custom_source(body)
    except PluginServiceError as exc:
        raise ApiError(str(exc)) from exc
    return ok({"sources": sources}, message="保存成功")


@router.put("/plugin-sources")
async def replace_plugin_sources(
    request: Request,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    body = await _json_or_empty(request)
    try:
        sources = await service.replace_custom_sources(body)
    except PluginServiceError as exc:
        raise ApiError(str(exc)) from exc
    return ok({"sources": sources}, message="保存成功")


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
    _request: Request,
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
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/plugin/page/bridge-sdk.js",
    )


@router.get("/plugins")
async def list_plugins(
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/plugin/get",
    )


@router.get("/plugins/by-id")
async def get_plugin_by_id(
    request: Request,
    plugin_id: str = Query(...),
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/plugin/detail",
        query={"name": plugin_id},
    )


@router.delete("/plugins/by-id")
async def uninstall_plugin_by_id(
    request: Request,
    plugin_id: str = Query(...),
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/plugin/uninstall",
        json_body={"name": plugin_id, **body},
    )


@router.get("/plugins/config")
async def get_plugin_config_by_id(
    request: Request,
    plugin_id: str = Query(...),
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/config/get",
        query={"plugin_name": plugin_id},
    )


@router.put("/plugins/config")
async def update_plugin_config_by_id(
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    plugin_id = _plugin_id_from_body(body)
    config = body.get("config")
    config = config if isinstance(config, dict) else {}
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/config/plugin/update",
        query={"plugin_name": plugin_id},
        json_body=config,
    )


@router.get("/plugins/config/schema")
async def get_plugin_config_schema_by_id(
    request: Request,
    plugin_id: str = Query(...),
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/config/get",
        query={"plugin_name": plugin_id},
    )


@router.get("/plugins/config-files")
async def list_plugin_config_files_by_id(
    request: Request,
    plugin_id: str = Query(...),
    config_key: str = Query(...),
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/config/file/get",
        query={"scope": "plugin", "name": plugin_id, "key": config_key},
    )


@router.post("/plugins/config-files")
async def upload_plugin_config_files_by_id(
    request: Request,
    plugin_id: str = Query(...),
    config_key: str = Query(...),
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/config/file/upload",
        query={"scope": "plugin", "name": plugin_id, "key": config_key},
    )


@router.delete("/plugins/config-files")
async def delete_plugin_config_file_by_id(
    request: Request,
    plugin_id: str = Query(...),
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/config/file/delete",
        query={"scope": "plugin", "name": plugin_id},
        json_body=body,
    )


@router.get("/plugins/readme")
async def get_plugin_readme_by_id(
    request: Request,
    plugin_id: str = Query(...),
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/plugin/readme",
        query={"name": plugin_id},
    )


@router.get("/plugins/changelog")
async def get_plugin_changelog_by_id(
    request: Request,
    plugin_id: str = Query(...),
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/plugin/changelog",
        query={"name": plugin_id},
    )


@router.post("/plugins/reload")
async def reload_plugin_by_id(
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    plugin_id = _plugin_id_from_body(body)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/plugin/reload",
        json_body={"name": plugin_id},
    )


@router.patch("/plugins/enabled")
async def set_plugin_enabled_by_id(
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    plugin_id = _plugin_id_from_body(body)
    target_path = "/api/plugin/on" if body.get("enabled") else "/api/plugin/off"
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path=target_path,
        json_body={"name": plugin_id},
    )


@router.get("/plugins/pages")
async def list_plugin_pages_by_id(
    request: Request,
    plugin_id: str = Query(...),
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/plugin/detail",
        query={"name": plugin_id},
    )


@router.get("/plugins/page")
async def get_plugin_page_by_id(
    request: Request,
    plugin_id: str = Query(...),
    page_name: str = Query(...),
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/plugin/page/entry",
        query={"name": plugin_id, "page": page_name},
    )


@router.get("/plugins/page/assets")
async def get_plugin_page_asset_by_id(
    request: Request,
    plugin_id: str = Query(...),
    page_name: str = Query(...),
    asset_path: str = Query(...),
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path=f"/api/plugin/page/content/{plugin_id}/{page_name}/{asset_path}",
    )


@router.get("/plugins/{plugin_id}")
async def get_plugin(
    plugin_id: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/plugin/detail",
        query={"name": plugin_id},
    )


@router.delete("/plugins/{plugin_id}")
async def uninstall_plugin(
    plugin_id: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/plugin/uninstall",
        json_body={"name": plugin_id, **body},
    )


@router.delete("/plugins/failed/{plugin_id}")
async def uninstall_failed_plugin(
    plugin_id: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/plugin/uninstall-failed",
        json_body={"dir_name": plugin_id, **body},
    )


@router.post("/plugins/failed/{plugin_id}/reload")
async def reload_failed_plugin(
    plugin_id: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/plugin/reload-failed",
        json_body={"dir_name": plugin_id},
    )


@router.get("/plugins/{plugin_id}/config")
async def get_plugin_config(
    plugin_id: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/config/get",
        query={"plugin_name": plugin_id},
    )


@router.put("/plugins/{plugin_id}/config")
async def update_plugin_config(
    plugin_id: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/config/plugin/update",
        query={"plugin_name": plugin_id},
    )


@router.get("/plugins/{plugin_id}/config/schema")
async def get_plugin_config_schema(
    plugin_id: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/config/get",
        query={"plugin_name": plugin_id},
    )


@router.get("/plugins/{plugin_id}/config-files/{config_key:path}")
async def list_plugin_config_files(
    plugin_id: str,
    config_key: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/config/file/get",
        query={"scope": "plugin", "name": plugin_id, "key": config_key},
    )


@router.post("/plugins/{plugin_id}/config-files/{config_key:path}")
async def upload_plugin_config_files(
    plugin_id: str,
    config_key: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/config/file/upload",
        query={"scope": "plugin", "name": plugin_id, "key": config_key},
    )


@router.delete("/plugins/{plugin_id}/config-files")
async def delete_plugin_config_file(
    plugin_id: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/config/file/delete",
        query={"scope": "plugin", "name": plugin_id},
        json_body=body,
    )


@router.get("/plugins/{plugin_id}/readme")
async def get_plugin_readme(
    plugin_id: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/plugin/readme",
        query={"name": plugin_id},
    )


@router.get("/plugins/{plugin_id}/changelog")
async def get_plugin_changelog(
    plugin_id: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/plugin/changelog",
        query={"name": plugin_id},
    )


@router.post("/plugins/{plugin_id}/reload")
async def reload_plugin(
    plugin_id: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/plugin/reload",
        json_body={"name": plugin_id},
    )


@router.patch("/plugins/{plugin_id}/enabled")
async def set_plugin_enabled(
    plugin_id: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    target_path = "/api/plugin/on" if body.get("enabled") else "/api/plugin/off"
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path=target_path,
        json_body={"name": plugin_id},
    )


@router.post("/plugins/{plugin_id}/update")
async def update_plugin(
    plugin_id: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/plugin/update",
        json_body={"name": plugin_id, **body},
    )


@router.get("/plugins/{plugin_id}/pages")
async def list_plugin_pages(
    plugin_id: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/plugin/detail",
        query={"name": plugin_id},
    )


@router.get("/plugins/{plugin_id}/pages/{page_name}")
async def get_plugin_page(
    plugin_id: str,
    page_name: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/plugin/page/entry",
        query={"name": plugin_id, "page": page_name},
    )


@router.get("/plugins/{plugin_id}/pages/{page_name}/assets/{asset_path:path}")
async def get_plugin_page_asset(
    plugin_id: str,
    page_name: str,
    asset_path: str,
    request: Request,
    auth: AuthContext = Depends(require_plugin_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path=f"/api/plugin/page/content/{plugin_id}/{page_name}/{asset_path}",
    )
