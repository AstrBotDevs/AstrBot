from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import (
    McpServerByNameRequest,
    McpServerRequest,
    ModelScopeSyncRequest,
    ToolEnabledRequest,
    ToolPermissionRequest,
)
from astrbot.dashboard.services.tools_service import (
    ToolsService,
    ToolsServiceError,
    extract_mcp_server_config,
)

from .auth import AuthContext, require_dashboard_user, require_scope

router = APIRouter(tags=["Extension Components"])
legacy_router = APIRouter(
    prefix="/api",
    tags=["Dashboard Extension Components"],
    include_in_schema=False,
)
oauth_callback_router = APIRouter(
    tags=["Dashboard Extension Components"],
    include_in_schema=False,
)


def get_service(request: Request) -> ToolsService:
    return request.app.state.services.tools


async def require_tool_scope(request: Request) -> AuthContext:
    return await require_scope(request, "tool")


async def require_mcp_scope(request: Request) -> AuthContext:
    return await require_scope(request, "mcp")


async def _json_or_empty(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _required_text(value: object, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ApiError(f"Missing key: {name}")
    return text


def _model_dict(payload: McpServerRequest | McpServerByNameRequest) -> dict[str, Any]:
    return payload.model_dump(exclude_none=True)


def _normalize_server_config(body: dict[str, Any], id_key: str) -> dict[str, Any]:
    config = body.get("config")
    if isinstance(config, dict):
        normalized = dict(config)
    else:
        normalized = {
            key: value
            for key, value in body.items()
            if key not in {id_key, "config", "enabled", "mcp_server_config"}
        }
    if "enabled" in body and "active" not in normalized:
        normalized["active"] = body["enabled"]
    return normalized


def _server_name_from_body(body: dict[str, Any]) -> str:
    return _required_text(body.get("server_name") or body.get("name"), "server_name")


def _test_config_body(
    service: ToolsService,
    server_name: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    config = body.get("mcp_server_config") or body.get("config")
    if isinstance(config, dict):
        return dict(config)

    stored_config = service.get_mcp_server_config(server_name)
    if stored_config is not None:
        return stored_config

    return {"name": server_name}


def _mcp_oauth_config_body(body: dict[str, Any]) -> dict[str, Any]:
    config = body.get("mcp_server_config") or body.get("config")
    if not isinstance(config, dict) or not config:
        raise ApiError("Invalid MCP server configuration")

    if "mcpServers" in config:
        try:
            config = extract_mcp_server_config(config["mcpServers"])
        except ValueError as exc:
            raise ApiError(f"{exc!s}") from exc

    return dict(config)


def _raise_tools_error(exc: ToolsServiceError) -> None:
    raise ApiError(str(exc)) from exc


async def _run(
    operation, *, result_as_message: bool = False, message: str | None = None
):
    try:
        result = await run_maybe_async(operation)
        if result_as_message:
            return ok(None, str(result))
        return ok(result, message)
    except ToolsServiceError as exc:
        _raise_tools_error(exc)


async def _toggle_tool(
    tool_id: str,
    enabled: bool,
    service: ToolsService,
):
    return await _run(
        lambda: service.toggle_tool({"name": tool_id, "activate": enabled}),
        result_as_message=True,
    )


async def _create_mcp_server(body: dict[str, Any], service: ToolsService):
    if "enabled" in body and "active" not in body:
        body["active"] = body.pop("enabled")
    return await _run(
        lambda: service.add_mcp_server(body),
        result_as_message=True,
    )


async def _update_mcp_server(
    server_name: str,
    body: dict[str, Any],
    service: ToolsService,
):
    config = _normalize_server_config(body, "server_name")
    config.setdefault("name", server_name)
    config.setdefault("oldName", server_name)
    return await _run(
        lambda: service.update_mcp_server(config),
        result_as_message=True,
    )


async def _delete_mcp_server(server_name: str, service: ToolsService):
    return await _run(
        lambda: service.delete_mcp_server({"name": server_name}),
        result_as_message=True,
    )


async def _test_mcp_server(
    server_name: str,
    body: dict[str, Any],
    service: ToolsService,
):
    config = _test_config_body(service, server_name, body)
    return await _run(
        lambda: service.test_mcp_connection(
            {"name": server_name, "mcp_server_config": config}
        ),
        message="🎉 MCP server is available!",
    )


async def _sync_modelscope_mcp_servers(
    access_token: str,
    service: ToolsService,
):
    return await _run(
        lambda: service.sync_provider(
            {
                "name": "modelscope",
                "access_token": access_token,
            }
        ),
        result_as_message=True,
    )


async def _start_mcp_oauth_authorization(
    request: Request,
    service: ToolsService,
):
    body = await _json_or_empty(request)
    config = _mcp_oauth_config_body(body)

    core_lifecycle = request.app.state.core_lifecycle
    callback_api_base = core_lifecycle.astrbot_config.get("callback_api_base", "")
    callback_base_value = (
        callback_api_base or body.get("callback_base_url") or str(request.base_url)
    )
    callback_base_url = str(callback_base_value).rstrip("/")
    server_name = request.query_params.get("name")

    return await _run(
        lambda: service.start_mcp_oauth_authorization(
            config,
            callback_base_url=callback_base_url,
            server_name=server_name,
            force=bool(body.get("force", False)),
        ),
        message="OAuth 2.0 authorization flow is ready.",
    )


async def _get_mcp_oauth_status(flow_id: str, service: ToolsService):
    flow_id = flow_id.strip()
    if not flow_id:
        raise ApiError("Missing required parameter: flow_id")
    return await _run(lambda: service.get_mcp_oauth_flow_status(flow_id))


@router.get("/tools")
async def list_tools(
    _auth: AuthContext = Depends(require_tool_scope),
    service: ToolsService = Depends(get_service),
):
    return await _run(service.get_tool_list)


@router.patch("/tools/{tool_id:path}/enabled")
async def set_tool_enabled(
    tool_id: str,
    payload: ToolEnabledRequest,
    _auth: AuthContext = Depends(require_tool_scope),
    service: ToolsService = Depends(get_service),
):
    return await _toggle_tool(tool_id, payload.enabled, service)


@router.patch("/tools/{tool_id:path}/permission")
async def set_tool_permission(
    tool_id: str,
    payload: ToolPermissionRequest,
    _auth: AuthContext = Depends(require_tool_scope),
    service: ToolsService = Depends(get_service),
):
    return await _run(
        lambda: service.update_tool_permission(
            {"name": tool_id, "permission": payload.permission}
        ),
        result_as_message=True,
    )


@router.get("/mcp/servers")
async def list_mcp_servers(
    _auth: AuthContext = Depends(require_mcp_scope),
    service: ToolsService = Depends(get_service),
):
    return await _run(service.get_mcp_servers)


@router.post("/mcp/servers")
async def create_mcp_server(
    payload: McpServerRequest,
    _auth: AuthContext = Depends(require_mcp_scope),
    service: ToolsService = Depends(get_service),
):
    return await _create_mcp_server(_model_dict(payload), service)


@router.put("/mcp/servers/by-name")
async def update_mcp_server_by_name(
    payload: McpServerByNameRequest,
    _auth: AuthContext = Depends(require_mcp_scope),
    service: ToolsService = Depends(get_service),
):
    body = _model_dict(payload)
    return await _update_mcp_server(payload.server_name, body, service)


@router.delete("/mcp/servers/by-name")
async def delete_mcp_server_by_name(
    server_name: str = Query(...),
    _auth: AuthContext = Depends(require_mcp_scope),
    service: ToolsService = Depends(get_service),
):
    return await _delete_mcp_server(server_name, service)


@router.patch("/mcp/servers/enabled")
async def set_mcp_server_enabled_by_name(
    payload: McpServerByNameRequest,
    _auth: AuthContext = Depends(require_mcp_scope),
    service: ToolsService = Depends(get_service),
):
    body = _model_dict(payload)
    return await _update_mcp_server(payload.server_name, body, service)


@router.post("/mcp/servers/test")
async def test_mcp_server_by_name(
    payload: McpServerByNameRequest,
    _auth: AuthContext = Depends(require_mcp_scope),
    service: ToolsService = Depends(get_service),
):
    body = _model_dict(payload)
    return await _test_mcp_server(payload.server_name, body, service)


@router.patch("/mcp/servers/{server_name:path}/enabled")
async def set_mcp_server_enabled(
    server_name: str,
    payload: ToolEnabledRequest,
    _auth: AuthContext = Depends(require_mcp_scope),
    service: ToolsService = Depends(get_service),
):
    return await _update_mcp_server(
        server_name,
        {"server_name": server_name, "enabled": payload.enabled},
        service,
    )


@router.post("/mcp/servers/{server_name:path}/test")
async def test_mcp_server(
    server_name: str,
    payload: McpServerRequest | None = None,
    _auth: AuthContext = Depends(require_mcp_scope),
    service: ToolsService = Depends(get_service),
):
    body = _model_dict(payload) if payload is not None else {}
    return await _test_mcp_server(server_name, body, service)


@router.put("/mcp/servers/{server_name:path}")
async def update_mcp_server(
    server_name: str,
    payload: McpServerRequest,
    _auth: AuthContext = Depends(require_mcp_scope),
    service: ToolsService = Depends(get_service),
):
    body = _model_dict(payload)
    return await _update_mcp_server(server_name, body, service)


@router.delete("/mcp/servers/{server_name:path}")
async def delete_mcp_server(
    server_name: str,
    _auth: AuthContext = Depends(require_mcp_scope),
    service: ToolsService = Depends(get_service),
):
    return await _delete_mcp_server(server_name, service)


@router.post("/mcp/providers/modelscope/sync")
async def sync_modelscope_mcp_servers(
    payload: ModelScopeSyncRequest | None = None,
    _auth: AuthContext = Depends(require_mcp_scope),
    service: ToolsService = Depends(get_service),
):
    access_token = payload.access_token if payload is not None else ""
    return await _sync_modelscope_mcp_servers(access_token or "", service)


@legacy_router.get("/tools/list")
async def list_dashboard_tools(
    _username: str = Depends(require_dashboard_user),
    service: ToolsService = Depends(get_service),
):
    return await _run(service.get_tool_list)


@legacy_router.post("/tools/toggle-tool")
async def toggle_dashboard_tool(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: ToolsService = Depends(get_service),
):
    body = await _json_or_empty(request)
    tool_id = _required_text(body.get("name"), "name")
    return await _toggle_tool(tool_id, bool(body.get("activate")), service)


@legacy_router.post("/tools/permission")
async def update_dashboard_tool_permission(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: ToolsService = Depends(get_service),
):
    body = await _json_or_empty(request)
    tool_id = _required_text(body.get("name"), "name")
    return await _run(
        lambda: service.update_tool_permission(
            {"name": tool_id, "permission": body.get("permission")}
        ),
        result_as_message=True,
    )


@legacy_router.get("/tools/mcp/servers")
async def list_dashboard_mcp_servers(
    _username: str = Depends(require_dashboard_user),
    service: ToolsService = Depends(get_service),
):
    return await _run(service.get_mcp_servers)


@legacy_router.post("/tools/mcp/add")
async def add_dashboard_mcp_server(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: ToolsService = Depends(get_service),
):
    return await _create_mcp_server(await _json_or_empty(request), service)


@legacy_router.post("/tools/mcp/update")
async def update_dashboard_mcp_server(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: ToolsService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _update_mcp_server(_server_name_from_body(body), body, service)


@legacy_router.post("/tools/mcp/delete")
async def delete_dashboard_mcp_server(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: ToolsService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _delete_mcp_server(_required_text(body.get("name"), "name"), service)


@legacy_router.post("/tools/mcp/test")
async def test_dashboard_mcp_connection(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: ToolsService = Depends(get_service),
):
    body = await _json_or_empty(request)
    server_name = str(body.get("name") or "")
    config = body.get("mcp_server_config") or body.get("config") or body
    return await _run(
        lambda: service.test_mcp_connection(
            {
                "name": server_name,
                "mcp_server_config": config,
            }
        ),
        message="🎉 MCP server is available!",
    )


@legacy_router.post("/tools/mcp/oauth/start")
async def start_dashboard_mcp_oauth_authorization(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: ToolsService = Depends(get_service),
):
    return await _start_mcp_oauth_authorization(request, service)


@legacy_router.get("/tools/mcp/oauth/status")
async def get_dashboard_mcp_oauth_status(
    flow_id: str = Query(""),
    _username: str = Depends(require_dashboard_user),
    service: ToolsService = Depends(get_service),
):
    return await _get_mcp_oauth_status(flow_id, service)


@legacy_router.post("/tools/mcp/sync-provider")
async def sync_dashboard_mcp_provider(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: ToolsService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(
        lambda: service.sync_provider(body),
        result_as_message=True,
    )


@oauth_callback_router.get("/mcp/oauth/callback", response_class=HTMLResponse)
async def handle_mcp_oauth_callback(
    request: Request,
    service: ToolsService = Depends(get_service),
):
    error = request.query_params.get("error")
    error_description = request.query_params.get("error_description")
    if error_description:
        error = f"{error or 'oauth_error'}: {error_description}"

    try:
        await service.submit_mcp_oauth_callback(
            None,
            code=request.query_params.get("code"),
            state=request.query_params.get("state"),
            error=error,
        )
    except KeyError:
        return HTMLResponse(
            "<html><body><h3>OAuth flow not found or expired.</h3></body></html>",
            status_code=404,
        )
    except ToolsServiceError as exc:
        return HTMLResponse(
            f"<html><body><h3>OAuth callback failed: {exc!s}</h3></body></html>",
            status_code=500,
        )

    return HTMLResponse(
        """
<html>
  <body style="font-family: sans-serif; padding: 24px;">
    <h3>OAuth authorization completed.</h3>
    <p>You can return to AstrBot and wait for the status to update.</p>
    <script>
      window.close();
    </script>
  </body>
</html>
""",
    )
