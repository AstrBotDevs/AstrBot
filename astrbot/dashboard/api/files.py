from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.responses import error, ok
from astrbot.dashboard.services.chat_service import ChatService, ChatServiceError
from astrbot.dashboard.services.file_service import FileService, FileServiceError

from .auth import AuthContext, require_scope
from .multipart import UploadFileAdapter

router = APIRouter(tags=["Files"])
legacy_router = APIRouter(prefix="/api", include_in_schema=False)


def get_service(request: Request) -> FileService:
    return request.app.state.services.files


def get_chat_service(request: Request) -> ChatService:
    return request.app.state.services.chat


async def require_file_scope(request: Request) -> AuthContext:
    return await require_scope(request, "file")


async def _serve_token_file(file_token: str, service: FileService):
    try:
        return FileResponse(await service.resolve_token_file(file_token))
    except FileServiceError as exc:
        raise HTTPException(status_code=404) from exc


def _file_response(file_path: str, mimetype: str | None = None) -> FileResponse:
    if mimetype:
        return FileResponse(file_path, media_type=mimetype)
    return FileResponse(file_path)


async def _run_file(operation, *, error_message: str = "File access error"):
    try:
        result = await run_maybe_async(operation)
        return result
    except ChatServiceError as exc:
        return error(str(exc))
    except (FileNotFoundError, OSError):
        return error(error_message)


async def _upload_file(file: UploadFile, service: ChatService):
    result = await _run_file(
        lambda: service.save_uploaded_file(UploadFileAdapter(file))
    )
    if isinstance(result, dict) and result.get("status") == "error":
        return result
    return ok(result)


@router.get("/files/tokens/{file_token}")
async def get_token_file(
    file_token: str,
    service: FileService = Depends(get_service),
):
    return await _serve_token_file(file_token, service)


@router.post("/files")
async def upload_file(
    file: UploadFile = File(...),
    _auth: AuthContext = Depends(require_file_scope),
    service: ChatService = Depends(get_chat_service),
):
    return await _upload_file(file, service)


@router.get("/files/content")
async def get_file_by_name(
    filename: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_file_scope),
    service: ChatService = Depends(get_chat_service),
):
    result = await _run_file(lambda: service.resolve_webchat_file(filename))
    if isinstance(result, dict) and result.get("status") == "error":
        return result
    file_path, mimetype = result
    return _file_response(file_path, mimetype)


@router.get("/files/{attachment_id}")
@router.get("/files/{attachment_id}/content")
async def get_file(
    attachment_id: str,
    _auth: AuthContext = Depends(require_file_scope),
    service: ChatService = Depends(get_chat_service),
):
    result = await _run_file(lambda: service.resolve_attachment_file(attachment_id))
    if isinstance(result, dict) and result.get("status") == "error":
        return result
    file_path, mimetype = result
    return _file_response(file_path, mimetype)


@router.delete("/files/{attachment_id}")
async def delete_file(
    attachment_id: str,
    _auth: AuthContext = Depends(require_file_scope),
):
    return ok({"attachment_id": attachment_id})


@legacy_router.get("/file/{file_token}")
async def get_dashboard_token_file(
    file_token: str,
    service: FileService = Depends(get_service),
):
    return await _serve_token_file(file_token, service)
