from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from astrbot.dashboard.services.route_bridge_service import DashboardRouteBridgeService

from ...auth import AuthContext
from .common import (
    auth_optional,
    get_bridge,
    require_config_scope,
    require_system_scope,
)

router = APIRouter(tags=["Auth"])


@router.post("/auth/login")
async def login(
    request: Request,
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, None, method="POST", target_path="/api/auth/login"
    )


@router.post("/auth/logout")
async def logout(
    request: Request,
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, None, method="POST", target_path="/api/auth/logout"
    )


@router.get("/auth/setup-status")
async def setup_status(
    request: Request,
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, None, method="GET", target_path="/api/auth/setup-status"
    )


@router.post("/auth/setup")
async def setup(
    request: Request,
    auth: AuthContext | None = Depends(auth_optional),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    target_path = "/api/auth/setup-authenticated" if auth else "/api/auth/setup"
    return await bridge.forward(request, auth, method="POST", target_path=target_path)


@router.post("/auth/totp/setup")
async def totp_setup(
    request: Request,
    auth: AuthContext | None = Depends(auth_optional),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/auth/totp/setup"
    )


@router.post("/auth/totp/recovery")
async def totp_recovery(
    request: Request,
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, None, method="POST", target_path="/api/auth/totp/recovery"
    )


@router.get("/system-config/runtime")
async def get_system_config_runtime(
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/config/get"
    )


@router.patch("/auth/account")
async def update_account(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/auth/account/edit"
    )


@router.get("/api-keys")
async def list_api_keys(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/apikey/list"
    )


@router.post("/api-keys")
async def create_api_key(
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/apikey/create"
    )


@router.post("/api-keys/{key_id}/revoke")
async def revoke_api_key(
    key_id: str,
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/apikey/revoke",
        json_body={"key_id": key_id},
    )


@router.delete("/api-keys/{key_id}")
async def delete_api_key(
    key_id: str,
    request: Request,
    auth: AuthContext = Depends(require_system_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/apikey/delete",
        json_body={"key_id": key_id},
    )
