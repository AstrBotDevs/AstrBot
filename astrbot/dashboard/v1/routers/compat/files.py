from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from astrbot.dashboard.services.route_bridge_service import DashboardRouteBridgeService

from ...auth import AuthContext
from .common import get_bridge, require_file_scope

router = APIRouter(tags=["Files"])


@router.post("/files")
async def upload_file(
    request: Request,
    auth: AuthContext = Depends(require_file_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/chat/post_file"
    )


@router.get("/files/content")
async def get_file_by_name(
    request: Request,
    auth: AuthContext = Depends(require_file_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/chat/get_file"
    )


@router.get("/files/tokens/{file_token}")
async def get_token_file(
    file_token: str,
    request: Request,
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        None,
        method="GET",
        target_path=f"/api/file/{file_token}",
    )


@router.get("/files/{attachment_id}")
@router.get("/files/{attachment_id}/content")
async def get_file(
    attachment_id: str,
    request: Request,
    auth: AuthContext = Depends(require_file_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/chat/get_attachment",
        query={"attachment_id": attachment_id},
    )


@router.delete("/files/{attachment_id}")
async def delete_file(
    attachment_id: str,
    _request: Request,
    _auth: AuthContext = Depends(require_file_scope),
):
    return {"status": "ok", "data": {"attachment_id": attachment_id}}
