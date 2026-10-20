from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.responses import error, ok
from astrbot.dashboard.schemas import ChatProjectRequest
from astrbot.dashboard.services.chatui_project_service import (
    ChatUIProjectService,
    ChatUIProjectServiceError,
)

from .auth import AuthContext, ScopeDependency, require_dashboard_user

router = APIRouter(tags=["Chat Projects"])
legacy_router = APIRouter(
    prefix="/api/chatui_project",
    tags=["Dashboard Chat Projects"],
    include_in_schema=False,
)


def get_service(request: Request) -> ChatUIProjectService:
    return request.app.state.services.chat_projects


require_chat_scope = ScopeDependency("chat")


async def _json_or_empty(request: Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _model_dict(payload) -> dict:
    return payload.model_dump(exclude_none=True)


async def _run(operation):
    try:
        result = await run_maybe_async(operation)
        return ok(result)
    except ChatUIProjectServiceError as exc:
        return error(str(exc))


@router.get("/chat/projects")
async def list_chat_projects(
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatUIProjectService = Depends(get_service),
):
    return await _run(lambda: service.list_projects(auth.username))


@legacy_router.get("/list")
async def list_dashboard_chat_projects(
    username: str = Depends(require_dashboard_user),
    service: ChatUIProjectService = Depends(get_service),
):
    return await _run(lambda: service.list_projects(username))


@router.post("/chat/projects")
async def create_chat_project(
    payload: ChatProjectRequest,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatUIProjectService = Depends(get_service),
):
    return await _run(
        lambda: service.create_project(auth.username, _model_dict(payload))
    )


@legacy_router.post("/create")
async def create_dashboard_chat_project(
    request: Request,
    username: str = Depends(require_dashboard_user),
    service: ChatUIProjectService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.create_project(username, body))


@router.get("/chat/projects/{project_id}")
async def get_chat_project(
    project_id: str,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatUIProjectService = Depends(get_service),
):
    return await _run(lambda: service.get_project(auth.username, project_id))


@legacy_router.get("/get")
async def get_dashboard_chat_project(
    project_id: str | None = Query(default=None),
    username: str = Depends(require_dashboard_user),
    service: ChatUIProjectService = Depends(get_service),
):
    return await _run(lambda: service.get_project_from_query(username, project_id))


@router.patch("/chat/projects/{project_id}")
async def update_chat_project(
    project_id: str,
    payload: ChatProjectRequest,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatUIProjectService = Depends(get_service),
):
    return await _run(
        lambda: service.update_project(
            auth.username,
            {"project_id": project_id, **_model_dict(payload)},
        )
    )


@legacy_router.post("/update")
async def update_dashboard_chat_project(
    request: Request,
    username: str = Depends(require_dashboard_user),
    service: ChatUIProjectService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.update_project(username, body))


@router.delete("/chat/projects/{project_id}")
async def delete_chat_project(
    project_id: str,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatUIProjectService = Depends(get_service),
):
    return await _run(lambda: service.delete_project(auth.username, project_id))


@legacy_router.get("/delete")
async def delete_dashboard_chat_project(
    project_id: str | None = Query(default=None),
    username: str = Depends(require_dashboard_user),
    service: ChatUIProjectService = Depends(get_service),
):
    return await _run(lambda: service.delete_project_from_query(username, project_id))


@router.get("/chat/projects/{project_id}/sessions")
async def list_chat_project_sessions(
    project_id: str,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatUIProjectService = Depends(get_service),
):
    return await _run(lambda: service.get_project_sessions(auth.username, project_id))


@router.get("/chat/projects/{project_id}/workspace/files")
async def list_chat_project_workspace_files(
    project_id: str,
    path: str = Query(default=""),
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatUIProjectService = Depends(get_service),
):
    return await _run(
        lambda: service.list_workspace_files(auth.username, project_id, path)
    )


@router.get("/chat/projects/{project_id}/workspace/file")
async def get_chat_project_workspace_file(
    project_id: str,
    path: str,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatUIProjectService = Depends(get_service),
):
    return await _run(
        lambda: service.get_workspace_file(auth.username, project_id, path)
    )


@router.get("/chat/projects/{project_id}/workspace/file/download")
async def download_chat_project_workspace_file(
    project_id: str,
    path: str,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatUIProjectService = Depends(get_service),
):
    try:
        workspace_root, file_path = await service.get_workspace_file_location(
            auth.username,
            project_id,
            path,
        )
    except ChatUIProjectServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    workspace_root_path = os.path.normcase(os.path.realpath(workspace_root))
    download_path = os.path.normcase(os.path.realpath(file_path))
    workspace_root_prefix = os.path.join(workspace_root_path, "")
    if download_path != workspace_root_path and not download_path.startswith(
        workspace_root_prefix
    ):
        raise HTTPException(status_code=400, detail="Invalid workspace path")
    return FileResponse(download_path, filename=os.path.basename(download_path))


@legacy_router.get("/get_sessions")
async def list_dashboard_chat_project_sessions(
    project_id: str | None = Query(default=None),
    username: str = Depends(require_dashboard_user),
    service: ChatUIProjectService = Depends(get_service),
):
    return await _run(
        lambda: service.get_project_sessions_from_query(username, project_id)
    )


@router.post("/chat/projects/{project_id}/sessions/{session_id}")
async def add_chat_project_session(
    project_id: str,
    session_id: str,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatUIProjectService = Depends(get_service),
):
    return await _run(
        lambda: service.add_session_to_project(
            auth.username,
            {"project_id": project_id, "session_id": session_id},
        )
    )


@legacy_router.post("/add_session")
async def add_dashboard_chat_project_session(
    request: Request,
    username: str = Depends(require_dashboard_user),
    service: ChatUIProjectService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.add_session_to_project(username, body))


@router.delete("/chat/projects/sessions/{session_id}")
async def remove_chat_project_session(
    session_id: str,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatUIProjectService = Depends(get_service),
):
    return await _run(
        lambda: service.remove_session_from_project(
            auth.username,
            {"session_id": session_id},
        )
    )


@legacy_router.post("/remove_session")
async def remove_dashboard_chat_project_session(
    request: Request,
    username: str = Depends(require_dashboard_user),
    service: ChatUIProjectService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.remove_session_from_project(username, body))
