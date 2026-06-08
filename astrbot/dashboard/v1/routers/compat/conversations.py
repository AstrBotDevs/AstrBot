from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from astrbot.dashboard.services.route_bridge_service import DashboardRouteBridgeService

from ...auth import AuthContext
from .common import get_bridge, require_data_scope
from .common import json_or_empty as _json_or_empty

router = APIRouter(tags=["Conversations"])


@router.get("/conversations")
async def list_conversations(
    request: Request,
    auth: AuthContext = Depends(require_data_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/conversation/list"
    )


@router.post("/conversations/export")
async def export_conversations(
    request: Request,
    auth: AuthContext = Depends(require_data_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/conversation/export"
    )


@router.post("/conversations/batch-delete")
async def batch_delete_conversations(
    request: Request,
    auth: AuthContext = Depends(require_data_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/conversation/delete"
    )


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    request: Request,
    auth: AuthContext = Depends(require_data_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    user_id = request.query_params.get("user_id")
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/conversation/detail",
        json_body={"user_id": user_id, "cid": conversation_id},
    )


@router.patch("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    request: Request,
    auth: AuthContext = Depends(require_data_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    user_id = body.pop("user_id", None) or request.query_params.get("user_id")
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/conversation/update",
        json_body={"user_id": user_id, "cid": conversation_id, **body},
    )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    request: Request,
    auth: AuthContext = Depends(require_data_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    user_id = request.query_params.get("user_id")
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/conversation/delete",
        json_body={"user_id": user_id, "cid": conversation_id},
    )


@router.put("/conversations/{conversation_id}/messages")
async def update_conversation_messages(
    conversation_id: str,
    request: Request,
    auth: AuthContext = Depends(require_data_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    user_id = body.pop("user_id", None) or request.query_params.get("user_id")
    if "messages" in body and "history" not in body:
        body["history"] = body.pop("messages")
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/conversation/update_history",
        json_body={"user_id": user_id, "cid": conversation_id, **body},
    )
