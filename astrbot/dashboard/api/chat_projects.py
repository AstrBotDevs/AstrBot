from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.responses import error, ok
from astrbot.dashboard.schemas import ChatProjectRequest
from astrbot.dashboard.services.chatui_project_service import (
    ChatUIProjectService,
    ChatUIProjectServiceError,
)

from .auth import AuthContext, require_scope

router = APIRouter(tags=["Chat Projects"])


def get_service(request: Request) -> ChatUIProjectService:
    return request.app.state.services.chat_projects


async def require_chat_scope(request: Request) -> AuthContext:
    return await require_scope(request, "chat")


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


@router.post("/chat/projects")
async def create_chat_project(
    payload: ChatProjectRequest,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatUIProjectService = Depends(get_service),
):
    return await _run(
        lambda: service.create_project(auth.username, _model_dict(payload))
    )


@router.get("/chat/projects/{project_id}")
async def get_chat_project(
    project_id: str,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatUIProjectService = Depends(get_service),
):
    return await _run(lambda: service.get_project(auth.username, project_id))


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


@router.delete("/chat/projects/{project_id}")
async def delete_chat_project(
    project_id: str,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatUIProjectService = Depends(get_service),
):
    return await _run(lambda: service.delete_project(auth.username, project_id))


@router.get("/chat/projects/{project_id}/sessions")
async def list_chat_project_sessions(
    project_id: str,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatUIProjectService = Depends(get_service),
):
    return await _run(lambda: service.get_project_sessions(auth.username, project_id))


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
    path: str = Query(...),
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatUIProjectService = Depends(get_service),
):
    return await _run(
        lambda: service.get_workspace_file(auth.username, project_id, path)
    )


@router.get(
    "/chat/projects/{project_id}/workspace/file/download",
    responses={
        200: {
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                }
            }
        }
    },
)
async def download_chat_project_workspace_file(
    project_id: str,
    path: str = Query(...),
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatUIProjectService = Depends(get_service),
):
    try:
        root, target = await service.get_workspace_file_location(
            auth.username,
            project_id,
            path,
        )
    except ChatUIProjectServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Re-check the ownership boundary immediately before constructing the response.
    if (
        not target.is_file()
        or target.is_symlink()
        or not target.resolve().is_relative_to(root)
    ):
        raise HTTPException(status_code=400, detail="Invalid workspace path")
    return FileResponse(target, filename=Path(path).name)
