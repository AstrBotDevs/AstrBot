from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from astrbot.dashboard.services.route_bridge_service import DashboardRouteBridgeService

from ...auth import AuthContext
from .common import get_bridge, require_persona_scope
from .common import json_or_empty as _json_or_empty

router = APIRouter(tags=["Personas"])


@router.get("/personas/tree")
async def persona_tree(
    request: Request,
    auth: AuthContext = Depends(require_persona_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/persona/folder/tree"
    )


@router.get("/personas")
async def list_personas(
    request: Request,
    auth: AuthContext = Depends(require_persona_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/persona/list"
    )


@router.post("/personas")
async def create_persona(
    request: Request,
    auth: AuthContext = Depends(require_persona_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/persona/create"
    )


@router.get("/personas/by-id")
async def get_persona_by_id(
    request: Request,
    persona_id: str = Query(...),
    auth: AuthContext = Depends(require_persona_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/persona/detail",
        json_body={"persona_id": persona_id},
    )


@router.put("/personas/by-id")
async def update_persona_by_id(
    request: Request,
    auth: AuthContext = Depends(require_persona_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    persona_id = str(body.get("persona_id") or "").strip()
    if not persona_id:
        raise ValueError("Missing key: persona_id")
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/persona/update",
        json_body={
            "persona_id": persona_id,
            **{key: value for key, value in body.items() if key != "persona_id"},
        },
    )


@router.delete("/personas/by-id")
async def delete_persona_by_id(
    request: Request,
    persona_id: str = Query(...),
    auth: AuthContext = Depends(require_persona_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/persona/delete",
        json_body={"persona_id": persona_id},
    )


@router.get("/personas/{persona_id:path}")
async def get_persona(
    persona_id: str,
    request: Request,
    auth: AuthContext = Depends(require_persona_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/persona/detail",
        json_body={"persona_id": persona_id},
    )


@router.put("/personas/{persona_id:path}")
async def update_persona(
    persona_id: str,
    request: Request,
    auth: AuthContext = Depends(require_persona_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/persona/update",
        json_body={"persona_id": persona_id, **body},
    )


@router.delete("/personas/{persona_id:path}")
async def delete_persona(
    persona_id: str,
    request: Request,
    auth: AuthContext = Depends(require_persona_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/persona/delete",
        json_body={"persona_id": persona_id},
    )


@router.post("/personas/move")
async def move_persona(
    request: Request,
    auth: AuthContext = Depends(require_persona_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/persona/move"
    )


@router.post("/personas/reorder")
async def reorder_personas(
    request: Request,
    auth: AuthContext = Depends(require_persona_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/persona/reorder"
    )


@router.get("/persona-folders")
async def list_persona_folders(
    request: Request,
    auth: AuthContext = Depends(require_persona_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/persona/folder/list"
    )


@router.post("/persona-folders")
async def create_persona_folder(
    request: Request,
    auth: AuthContext = Depends(require_persona_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/persona/folder/create"
    )


@router.put("/persona-folders/{folder_id}")
async def update_persona_folder(
    folder_id: str,
    request: Request,
    auth: AuthContext = Depends(require_persona_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/persona/folder/update",
        json_body={"folder_id": folder_id, **body},
    )


@router.delete("/persona-folders/{folder_id}")
async def delete_persona_folder(
    folder_id: str,
    request: Request,
    auth: AuthContext = Depends(require_persona_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/persona/folder/delete",
        json_body={"folder_id": folder_id},
    )
