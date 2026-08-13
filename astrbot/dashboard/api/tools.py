from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse, RedirectResponse

from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import (
    McpCompletionRequest,
    McpPromptGetRequest,
    McpResourceReadRequest,
    McpServerRequest,
    ModelScopeSyncRequest,
    ToolEnabledRequest,
)
from astrbot.dashboard.services.tools_service import ToolsService, ToolsServiceError

from .auth import AuthContext, require_scope

router = APIRouter(tags=["Extension Components"])


def get_service(request: Request) -> ToolsService:
    return request.app.state.services.tools


async def require_tool_scope(request: Request) -> AuthContext:
    return await require_scope(request, "tool")


async def require_mcp_scope(request: Request) -> AuthContext:
    return await require_scope(request, "mcp", action_override="tool.mcp_read")


async def require_mcp_write_scope(request: Request) -> AuthContext:
    return await require_scope(request, "mcp", action_override="tool.mcp_write")


def _model_dict(payload: McpServerRequest) -> dict[str, Any]:
    return payload.model_dump(exclude_none=True)


def _reject_legacy_server_config_fields(config: dict[str, Any]) -> dict[str, Any]:
    legacy_fields = [
        key
        for key in (
            "enabled",
            "mcpServers",
            "mcp_server_config",
            "oldName",
            "type",
            "sse_read_timeout",
            "session_read_timeout",
            "timeout",
            "config",
        )
        if key in config
    ]
    if legacy_fields:
        fields = ", ".join(sorted(legacy_fields))
        raise ApiError(f"Legacy MCP config fields are not supported: {fields}")
    return config


def _normalize_server_config(body: dict[str, Any], id_key: str) -> dict[str, Any]:
    normalized = {key: value for key, value in body.items() if key != id_key}
    return _reject_legacy_server_config_fields(normalized)


def _test_config_body(
    service: ToolsService,
    server_name: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    if body:
        return _reject_legacy_server_config_fields(
            {key: value for key, value in body.items() if key != "name"}
        )

    stored_config = service.get_mcp_server_config(server_name)
    if stored_config is not None:
        return stored_config

    return {"name": server_name}


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
    return await _run(
        lambda: service.update_mcp_server(server_name, config),
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
        lambda: service.test_mcp_connection({"name": server_name, "config": config}),
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


@router.get("/tools")
async def list_tools(
    _auth: AuthContext = Depends(require_tool_scope),
    service: ToolsService = Depends(get_service),
):
    return await _run(service.get_tool_list)


@router.patch("/tools/parallel/enabled")
async def set_parallel_enabled(
    payload: ToolEnabledRequest,
    _auth: AuthContext = Depends(require_tool_scope),
    service: ToolsService = Depends(get_service),
):
    return await _run(
        lambda: service.set_parallel_enabled(payload.enabled),
        result_as_message=True,
    )


@router.patch("/tools/{tool_id:path}/enabled")
async def set_tool_enabled(
    tool_id: str,
    payload: ToolEnabledRequest,
    _auth: AuthContext = Depends(require_tool_scope),
    service: ToolsService = Depends(get_service),
):
    return await _toggle_tool(tool_id, payload.enabled, service)


@router.patch("/tools/{tool_id:path}/parallel")
async def set_tool_parallel(
    tool_id: str,
    payload: ToolEnabledRequest,
    _auth: AuthContext = Depends(require_tool_scope),
    service: ToolsService = Depends(get_service),
):
    return await _run(
        lambda: service.toggle_tool_parallel(
            {"tool_id": tool_id, "enabled": payload.enabled}
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
    _auth: AuthContext = Depends(require_mcp_write_scope),
    service: ToolsService = Depends(get_service),
):
    return await _create_mcp_server(_model_dict(payload), service)


@router.patch("/mcp/servers/{server_name:path}/enabled")
async def set_mcp_server_enabled(
    server_name: str,
    payload: ToolEnabledRequest,
    _auth: AuthContext = Depends(require_mcp_write_scope),
    service: ToolsService = Depends(get_service),
):
    return await _run(
        lambda: service.update_mcp_server(
            server_name,
            {"name": server_name, "active": payload.enabled},
        ),
        result_as_message=True,
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


@router.get("/mcp/servers/{server_name:path}/catalog")
async def get_mcp_catalog(
    server_name: str,
    _auth: AuthContext = Depends(require_mcp_scope),
    service: ToolsService = Depends(get_service),
):
    return await _run(lambda: service.get_mcp_runtime_catalog(server_name))


@router.get("/mcp/servers/{server_name:path}/resources")
async def list_mcp_resources(
    server_name: str,
    _auth: AuthContext = Depends(require_mcp_scope),
    service: ToolsService = Depends(get_service),
):
    return await _run(lambda: service.list_mcp_resources(server_name))


@router.get("/mcp/servers/{server_name:path}/resources/templates")
async def list_mcp_resource_templates(
    server_name: str,
    _auth: AuthContext = Depends(require_mcp_scope),
    service: ToolsService = Depends(get_service),
):
    return await _run(lambda: service.list_mcp_resource_templates(server_name))


@router.post("/mcp/servers/{server_name:path}/resources/read")
async def read_mcp_resource(
    server_name: str,
    payload: McpResourceReadRequest,
    _auth: AuthContext = Depends(require_mcp_scope),
    service: ToolsService = Depends(get_service),
):
    return await _run(lambda: service.read_mcp_resource(server_name, payload.uri))


@router.get("/mcp/servers/{server_name:path}/prompts")
async def list_mcp_prompts(
    server_name: str,
    _auth: AuthContext = Depends(require_mcp_scope),
    service: ToolsService = Depends(get_service),
):
    return await _run(lambda: service.list_mcp_prompts(server_name))


@router.post("/mcp/servers/{server_name:path}/prompts/{prompt_name}/get")
async def get_mcp_prompt(
    server_name: str,
    prompt_name: str,
    payload: McpPromptGetRequest | None = None,
    _auth: AuthContext = Depends(require_mcp_scope),
    service: ToolsService = Depends(get_service),
):
    return await _run(
        lambda: service.get_mcp_prompt(
            server_name, prompt_name, payload.arguments if payload else None
        )
    )


@router.post("/mcp/servers/{server_name:path}/completion")
async def complete_mcp(
    server_name: str,
    payload: McpCompletionRequest,
    _auth: AuthContext = Depends(require_mcp_scope),
    service: ToolsService = Depends(get_service),
):
    return await _run(
        lambda: service.complete_mcp(
            server_name,
            payload.reference,
            payload.argument,
            payload.context_arguments,
        )
    )


@router.get("/mcp/servers/{server_name:path}/oauth/status")
async def get_mcp_oauth_status(
    server_name: str,
    _auth: AuthContext = Depends(require_mcp_scope),
    service: ToolsService = Depends(get_service),
):
    return await _run(lambda: service.get_mcp_auth_status(server_name))


@router.post("/mcp/servers/{server_name:path}/oauth/start")
async def start_mcp_oauth(
    server_name: str,
    _auth: AuthContext = Depends(require_mcp_write_scope),
    service: ToolsService = Depends(get_service),
):
    return await _run(lambda: service.start_mcp_authorization(server_name))


@router.delete("/mcp/servers/{server_name:path}/oauth")
async def revoke_mcp_oauth(
    server_name: str,
    _auth: AuthContext = Depends(require_mcp_write_scope),
    service: ToolsService = Depends(get_service),
):
    return await _run(lambda: service.revoke_mcp_authorization(server_name))


@router.get("/mcp/oauth/callback")
async def complete_mcp_oauth_callback(
    request: Request,
    service: ToolsService = Depends(get_service),
):
    """OAuth redirects are a protocol response, not a Dashboard envelope."""
    code = request.query_params.get("code", "")
    state = request.query_params.get("state")
    issuer = request.query_params.get("iss")
    if not await service.tool_mgr.mcp_authorization_coordinator.complete_callback_from_state(
        code, state, issuer
    ):
        return PlainTextResponse(
            "Invalid or expired MCP OAuth callback.", status_code=400
        )
    return RedirectResponse(url="/?mcp_oauth=complete", status_code=303)


@router.put("/mcp/servers/{server_name:path}")
async def update_mcp_server(
    server_name: str,
    payload: McpServerRequest,
    _auth: AuthContext = Depends(require_mcp_write_scope),
    service: ToolsService = Depends(get_service),
):
    body = _model_dict(payload)
    return await _update_mcp_server(server_name, body, service)


@router.delete("/mcp/servers/{server_name:path}")
async def delete_mcp_server(
    server_name: str,
    _auth: AuthContext = Depends(require_mcp_write_scope),
    service: ToolsService = Depends(get_service),
):
    return await _delete_mcp_server(server_name, service)


@router.post("/mcp/providers/modelscope/sync")
async def sync_modelscope_mcp_servers(
    payload: ModelScopeSyncRequest | None = None,
    _auth: AuthContext = Depends(require_mcp_write_scope),
    service: ToolsService = Depends(get_service),
):
    access_token = payload.access_token if payload is not None else ""
    return await _sync_modelscope_mcp_servers(access_token or "", service)
