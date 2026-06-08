from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from astrbot.dashboard.services.route_bridge_service import DashboardRouteBridgeService

from ..auth import AuthContext, require_scope

router = APIRouter(tags=["Extension Components"])


def get_bridge(request: Request) -> DashboardRouteBridgeService:
    return request.app.state.services.route_bridge


async def require_tool_scope(request: Request) -> AuthContext:
    return await require_scope(request, "tool")


async def require_skill_scope(request: Request) -> AuthContext:
    return await require_scope(request, "skill")


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


def _config_from_body(body: dict, id_key: str) -> dict:
    config = body.get("config")
    if isinstance(config, dict):
        return dict(config)
    return {
        key: value
        for key, value in body.items()
        if key not in {id_key, "config", "enabled"}
    }


@router.get("/commands")
async def list_commands(
    request: Request,
    auth: AuthContext = Depends(require_tool_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/commands",
    )


@router.get("/commands/conflicts")
async def list_command_conflicts(
    request: Request,
    auth: AuthContext = Depends(require_tool_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/commands/conflicts",
    )


@router.patch("/commands/{command_id}")
async def update_command(
    command_id: str,
    request: Request,
    auth: AuthContext = Depends(require_tool_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    if "enabled" in body:
        return await bridge.forward(
            request,
            auth,
            method="POST",
            target_path="/api/commands/toggle",
            json_body={
                "handler_full_name": command_id,
                "enabled": body["enabled"],
            },
        )
    if "alias" in body:
        return await bridge.forward(
            request,
            auth,
            method="POST",
            target_path="/api/commands/rename",
            json_body={
                "handler_full_name": command_id,
                "new_name": body["alias"],
                "aliases": body.get("aliases"),
            },
        )
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/commands/permission",
        json_body={
            "handler_full_name": command_id,
            "permission": body.get("permission_group"),
        },
    )


@router.get("/tools")
async def list_tools(
    request: Request,
    auth: AuthContext = Depends(require_tool_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/tools/list",
    )


@router.patch("/tools/{tool_id}/enabled")
async def set_tool_enabled(
    tool_id: str,
    request: Request,
    auth: AuthContext = Depends(require_tool_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/tools/toggle-tool",
        json_body={"name": tool_id, "activate": body.get("enabled")},
    )


@router.get("/mcp/servers")
async def list_mcp_servers(
    request: Request,
    auth: AuthContext = Depends(require_tool_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/tools/mcp/servers",
    )


@router.post("/mcp/servers")
async def create_mcp_server(
    request: Request,
    auth: AuthContext = Depends(require_tool_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    if "enabled" in body and "active" not in body:
        body["active"] = body.pop("enabled")
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/tools/mcp/add",
        json_body=body,
    )


@router.put("/mcp/servers/by-name")
async def update_mcp_server_by_name(
    request: Request,
    auth: AuthContext = Depends(require_tool_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    server_name = _required_text(body.get("server_name"), "server_name")
    config = _config_from_body(body, "server_name")
    if "enabled" in body and "active" not in config:
        config["active"] = body["enabled"]
    config.setdefault("name", server_name)
    config.setdefault("oldName", server_name)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/tools/mcp/update",
        json_body=config,
    )


@router.delete("/mcp/servers/by-name")
async def delete_mcp_server_by_name(
    server_name: str,
    request: Request,
    auth: AuthContext = Depends(require_tool_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/tools/mcp/delete",
        json_body={"name": server_name},
    )


@router.patch("/mcp/servers/enabled")
async def set_mcp_server_enabled_by_name(
    request: Request,
    auth: AuthContext = Depends(require_tool_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    server_name = _required_text(body.get("server_name"), "server_name")
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/tools/mcp/update",
        json_body={
            "name": server_name,
            "oldName": server_name,
            "active": body.get("enabled"),
        },
    )


@router.post("/mcp/servers/test")
async def test_mcp_server_by_name(
    request: Request,
    auth: AuthContext = Depends(require_tool_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    server_name = _required_text(body.get("server_name"), "server_name")
    config = body.get("mcp_server_config") or body.get("config")
    config = dict(config) if isinstance(config, dict) else {"name": server_name}
    config.setdefault("name", server_name)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/tools/mcp/test",
        json_body={"mcp_server_config": config},
    )


@router.patch("/mcp/servers/{server_name:path}/enabled")
async def set_mcp_server_enabled(
    server_name: str,
    request: Request,
    auth: AuthContext = Depends(require_tool_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/tools/mcp/update",
        json_body={
            "name": server_name,
            "oldName": server_name,
            "active": body.get("enabled"),
        },
    )


@router.post("/mcp/servers/{server_name:path}/test")
async def test_mcp_server(
    server_name: str,
    request: Request,
    auth: AuthContext = Depends(require_tool_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    config = body.get("mcp_server_config") or body or {"name": server_name}
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/tools/mcp/test",
        json_body={"mcp_server_config": config},
    )


@router.put("/mcp/servers/{server_name:path}")
async def update_mcp_server(
    server_name: str,
    request: Request,
    auth: AuthContext = Depends(require_tool_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    if "enabled" in body and "active" not in body:
        body["active"] = body.pop("enabled")
    body.setdefault("name", server_name)
    body.setdefault("oldName", server_name)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/tools/mcp/update",
        json_body=body,
    )


@router.delete("/mcp/servers/{server_name:path}")
async def delete_mcp_server(
    server_name: str,
    request: Request,
    auth: AuthContext = Depends(require_tool_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/tools/mcp/delete",
        json_body={"name": server_name},
    )


@router.post("/mcp/providers/modelscope/sync")
async def sync_modelscope_mcp_servers(
    request: Request,
    auth: AuthContext = Depends(require_tool_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/tools/mcp/sync-provider",
        json_body={
            "name": "modelscope",
            "access_token": body.get("access_token", ""),
        },
    )


@router.get("/skills")
async def list_skills(
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/skills",
    )


@router.post("/skills")
async def upload_skill(
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/skills/upload",
    )


@router.post("/skills/batch")
async def upload_skills_batch(
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/skills/batch-upload",
    )


@router.patch("/skills/by-name")
async def update_skill_by_name(
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    skill_name = _required_text(body.get("skill_name"), "skill_name")
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/skills/update",
        json_body={
            "name": skill_name,
            "active": body.get("enabled", body.get("active", True)),
        },
    )


@router.delete("/skills/by-name")
async def delete_skill_by_name(
    skill_name: str,
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/skills/delete",
        json_body={"name": skill_name},
    )


@router.get("/skills/archive")
async def download_skill_by_name(
    skill_name: str,
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/skills/download",
        query={"name": skill_name},
    )


@router.get("/skills/files")
async def list_skill_files_by_name(
    skill_name: str,
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    path = request.query_params.get("path", "")
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/skills/files",
        query={"name": skill_name, "path": path},
    )


@router.get("/skills/file")
async def get_skill_file_by_name(
    skill_name: str,
    path: str,
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/skills/file",
        query={"name": skill_name, "path": path},
    )


@router.put("/skills/file")
async def update_skill_file_by_name(
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    skill_name = _required_text(body.get("skill_name"), "skill_name")
    path = _required_text(body.get("path"), "path")
    content = str(body.get("content", ""))
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/skills/file",
        json_body={"name": skill_name, "path": path, "content": content},
    )


@router.get("/skills/{skill_name:path}/archive")
async def download_skill(
    skill_name: str,
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/skills/download",
        query={"name": skill_name},
    )


@router.get("/skills/{skill_name:path}/files")
async def list_skill_files(
    skill_name: str,
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    path = request.query_params.get("path", "")
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/skills/files",
        query={"name": skill_name, "path": path},
    )


@router.get("/skills/{skill_name:path}/files/{file_path:path}")
async def get_skill_file(
    skill_name: str,
    file_path: str,
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/skills/file",
        query={"name": skill_name, "path": file_path},
    )


@router.put("/skills/{skill_name:path}/files/{file_path:path}")
async def update_skill_file(
    skill_name: str,
    file_path: str,
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    content = (await request.body()).decode("utf-8")
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/skills/file",
        json_body={"name": skill_name, "path": file_path, "content": content},
    )


@router.patch("/skills/{skill_name:path}")
async def update_skill(
    skill_name: str,
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/skills/update",
        json_body={
            "name": skill_name,
            "active": body.get("enabled", body.get("active", True)),
        },
    )


@router.delete("/skills/{skill_name:path}")
async def delete_skill(
    skill_name: str,
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/skills/delete",
        json_body={"name": skill_name},
    )


@router.get("/skills/neo/candidates")
async def list_neo_skill_candidates(
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/skills/neo/candidates",
    )


@router.get("/skills/neo/releases")
async def list_neo_skill_releases(
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/skills/neo/releases",
    )


@router.get("/skills/neo/payload")
async def get_neo_skill_payload(
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/skills/neo/payload",
    )


@router.post("/skills/neo/evaluate")
async def evaluate_neo_skill_candidate(
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/skills/neo/evaluate",
    )


@router.post("/skills/neo/promote")
async def promote_neo_skill_candidate(
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/skills/neo/promote",
    )


@router.post("/skills/neo/rollback")
async def rollback_neo_skill_release(
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/skills/neo/rollback",
    )


@router.post("/skills/neo/sync")
async def sync_neo_skill_release(
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/skills/neo/sync",
    )


@router.post("/skills/neo/candidates/delete")
async def delete_neo_skill_candidate(
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/skills/neo/delete-candidate",
    )


@router.post("/skills/neo/releases/delete")
async def delete_neo_skill_release(
    request: Request,
    auth: AuthContext = Depends(require_skill_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/skills/neo/delete-release",
    )
