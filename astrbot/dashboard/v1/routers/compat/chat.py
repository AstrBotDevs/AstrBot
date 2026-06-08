from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from astrbot.dashboard.services.route_bridge_service import DashboardRouteBridgeService

from ...auth import AuthContext
from .common import get_bridge, require_chat_scope, require_config_scope
from .common import (
    json_or_empty as _json_or_empty,
)

router = APIRouter(tags=["Chat"])


@router.post("/bot-types/{bot_type}/registration")
async def register_bot_type(
    bot_type: str,
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path=f"/api/platform/registration/{bot_type}",
    )


@router.get("/chat/sessions/new")
async def create_chat_session(
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/chat/new_session"
    )


@router.post("/chat/sessions/batch-delete")
async def batch_delete_chat_sessions(
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/chat/batch_delete_sessions"
    )


@router.get("/chat/sessions/{session_id}")
async def get_chat_session(
    session_id: str,
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/chat/get_session",
        query={"session_id": session_id},
    )


@router.patch("/chat/sessions/{session_id}")
async def update_chat_session(
    session_id: str,
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/chat/update_session_display_name",
        json_body={"session_id": session_id, **body},
    )


@router.delete("/chat/sessions/{session_id}")
async def delete_chat_session(
    session_id: str,
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/chat/delete_session",
        query={"session_id": session_id},
    )


@router.post("/chat/sessions/{session_id}/stop")
async def stop_chat_session(
    session_id: str,
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/chat/stop",
        json_body={"session_id": session_id},
    )


@router.patch("/chat/sessions/{session_id}/messages/{message_id}")
async def update_chat_message(
    session_id: str,
    message_id: str,
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/chat/message/edit",
        json_body={"session_id": session_id, "message_id": message_id, **body},
    )


@router.post("/chat/sessions/{session_id}/messages/{message_id}/regenerate")
async def regenerate_chat_message(
    session_id: str,
    message_id: str,
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/chat/message/regenerate",
        json_body={"session_id": session_id, "message_id": message_id, **body},
    )


@router.get("/chat/configs")
async def chat_configs(
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/config/abconfs"
    )


@router.post("/chat/threads")
async def create_chat_thread(
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/chat/thread/create"
    )


@router.get("/chat/threads/{thread_id}")
async def get_chat_thread(
    thread_id: str,
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/chat/thread/get",
        query={"thread_id": thread_id},
    )


@router.delete("/chat/threads/{thread_id}")
async def delete_chat_thread(
    thread_id: str,
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/chat/thread/delete",
        json_body={"thread_id": thread_id},
    )


@router.post("/chat/threads/{thread_id}/messages")
async def send_chat_thread_message(
    thread_id: str,
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/chat/thread/send",
        json_body={"thread_id": thread_id, **body},
    )


@router.get("/chat/projects")
async def list_chat_projects(
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/chatui_project/list"
    )


@router.post("/chat/projects")
async def create_chat_project(
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/chatui_project/create"
    )


@router.get("/chat/projects/{project_id}")
async def get_chat_project(
    project_id: str,
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/chatui_project/get",
        query={"project_id": project_id},
    )


@router.patch("/chat/projects/{project_id}")
async def update_chat_project(
    project_id: str,
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/chatui_project/update",
        json_body={"project_id": project_id, **body},
    )


@router.delete("/chat/projects/{project_id}")
async def delete_chat_project(
    project_id: str,
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/chatui_project/delete",
        query={"project_id": project_id},
    )


@router.get("/chat/projects/{project_id}/sessions")
async def list_chat_project_sessions(
    project_id: str,
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/chatui_project/get_sessions",
        query={"project_id": project_id},
    )


@router.post("/chat/projects/{project_id}/sessions/{session_id}")
async def add_chat_project_session(
    project_id: str,
    session_id: str,
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/chatui_project/add_session",
        json_body={"project_id": project_id, "session_id": session_id},
    )


@router.delete("/chat/projects/sessions/{session_id}")
async def remove_chat_project_session(
    session_id: str,
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/chatui_project/remove_session",
        json_body={"session_id": session_id},
    )
