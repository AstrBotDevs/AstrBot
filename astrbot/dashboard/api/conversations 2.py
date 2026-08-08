from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import (
    ConversationBatchDeleteRequest,
    ConversationExportRequest,
    ConversationMessagesReplaceRequest,
    ConversationPatchRequest,
)
from astrbot.dashboard.services.conversation_service import (
    ConversationExport,
    ConversationService,
    ConversationServiceError,
)

from .auth import AuthContext, require_dashboard_user, require_scope

router = APIRouter(tags=["Conversations"])
legacy_router = APIRouter(
    prefix="/api/conversation",
    tags=["Dashboard Conversations"],
    include_in_schema=False,
)


def get_service(request: Request) -> ConversationService:
    return request.app.state.services.conversations


async def require_data_scope(request: Request) -> AuthContext:
    return await require_scope(request, "data")


async def _json_or_empty(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _model_dict(payload) -> dict[str, Any]:
    return payload.model_dump(exclude_none=True)


def _raise_conversation_error(exc: ConversationServiceError) -> None:
    raise ApiError(str(exc)) from exc


async def _run(operation):
    try:
        result = await run_maybe_async(operation)
        return ok(result)
    except ConversationServiceError as exc:
        _raise_conversation_error(exc)


def _export_response(export: ConversationExport) -> StreamingResponse:
    export.file_obj.seek(0)

    def iter_file():
        while chunk := export.file_obj.read(8192):
            yield chunk

    return StreamingResponse(
        iter_file(),
        media_type=export.mimetype,
        headers={"Content-Disposition": f'attachment; filename="{export.filename}"'},
    )


async def _export_conversations(
    payload: dict[str, Any],
    service: ConversationService,
):
    try:
        return _export_response(await service.export_conversations(payload))
    except ConversationServiceError as exc:
        _raise_conversation_error(exc)


async def _list_conversations(
    service: ConversationService,
    *,
    page: int,
    page_size: int,
    platforms: str,
    message_types: str,
    search: str,
    exclude_ids: str,
    exclude_platforms: str,
):
    return await _run(
        lambda: service.list_conversations(
            page=page,
            page_size=page_size,
            platforms=platforms,
            message_types=message_types,
            search_query=search,
            exclude_ids=exclude_ids,
            exclude_platforms=exclude_platforms,
        )
    )


@router.get("/conversations")
async def list_conversations(
    page: int = Query(default=1),
    page_size: int = Query(default=20),
    platforms: str = Query(default=""),
    message_types: str = Query(default=""),
    search: str = Query(default=""),
    exclude_ids: str = Query(default=""),
    exclude_platforms: str = Query(default=""),
    _auth: AuthContext = Depends(require_data_scope),
    service: ConversationService = Depends(get_service),
):
    return await _list_conversations(
        service,
        page=page,
        page_size=page_size,
        platforms=platforms,
        message_types=message_types,
        search=search,
        exclude_ids=exclude_ids,
        exclude_platforms=exclude_platforms,
    )


@router.post("/conversations/export")
async def export_conversations(
    payload: ConversationExportRequest,
    _auth: AuthContext = Depends(require_data_scope),
    service: ConversationService = Depends(get_service),
):
    return await _export_conversations(_model_dict(payload), service)


@router.post("/conversations/batch-delete")
async def batch_delete_conversations(
    payload: ConversationBatchDeleteRequest,
    _auth: AuthContext = Depends(require_data_scope),
    service: ConversationService = Depends(get_service),
):
    return await _run(lambda: service.delete_conversation(_model_dict(payload)))


@router.put("/conversations/{conversation_id:path}/messages")
async def replace_conversation_messages(
    conversation_id: str,
    payload: ConversationMessagesReplaceRequest,
    user_id: str = Query(...),
    _auth: AuthContext = Depends(require_data_scope),
    service: ConversationService = Depends(get_service),
):
    body = _model_dict(payload)
    body_user_id = body.pop("user_id", None) or user_id
    if "messages" in body and "history" not in body:
        body["history"] = body.pop("messages")
    return await _run(
        lambda: service.update_history(
            {"user_id": body_user_id, "cid": conversation_id, **body}
        )
    )


@router.get("/conversations/{conversation_id:path}")
async def get_conversation(
    conversation_id: str,
    user_id: str = Query(...),
    _auth: AuthContext = Depends(require_data_scope),
    service: ConversationService = Depends(get_service),
):
    return await _run(
        lambda: service.get_conversation_detail(
            {"user_id": user_id, "cid": conversation_id}
        )
    )


@router.patch("/conversations/{conversation_id:path}")
async def update_conversation(
    conversation_id: str,
    payload: ConversationPatchRequest,
    user_id: str = Query(...),
    _auth: AuthContext = Depends(require_data_scope),
    service: ConversationService = Depends(get_service),
):
    body = _model_dict(payload)
    body_user_id = body.pop("user_id", None) or user_id
    return await _run(
        lambda: service.update_conversation(
            {"user_id": body_user_id, "cid": conversation_id, **body}
        )
    )


@router.delete("/conversations/{conversation_id:path}")
async def delete_conversation(
    conversation_id: str,
    user_id: str = Query(...),
    _auth: AuthContext = Depends(require_data_scope),
    service: ConversationService = Depends(get_service),
):
    return await _run(
        lambda: service.delete_conversation(
            {"user_id": user_id, "cid": conversation_id}
        )
    )


@legacy_router.get("/list")
async def list_dashboard_conversations(
    page: int = Query(default=1),
    page_size: int = Query(default=20),
    platforms: str = Query(default=""),
    message_types: str = Query(default=""),
    search: str = Query(default=""),
    exclude_ids: str = Query(default=""),
    exclude_platforms: str = Query(default=""),
    _username: str = Depends(require_dashboard_user),
    service: ConversationService = Depends(get_service),
):
    return await _list_conversations(
        service,
        page=page,
        page_size=page_size,
        platforms=platforms,
        message_types=message_types,
        search=search,
        exclude_ids=exclude_ids,
        exclude_platforms=exclude_platforms,
    )


@legacy_router.post("/detail")
async def get_dashboard_conversation_detail(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: ConversationService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.get_conversation_detail(body))


@legacy_router.post("/update")
async def update_dashboard_conversation(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: ConversationService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.update_conversation(body))


@legacy_router.post("/delete")
async def delete_dashboard_conversation(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: ConversationService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.delete_conversation(body))


@legacy_router.post("/update_history")
async def update_dashboard_conversation_history(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: ConversationService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.update_history(body))


@legacy_router.post("/export")
async def export_dashboard_conversations(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: ConversationService = Depends(get_service),
):
    return await _export_conversations(await _json_or_empty(request), service)
