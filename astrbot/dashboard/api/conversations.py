from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from astrbot.core.auth.models import Resource
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

from .auth import AuthContext, object_resource, require_resource_action, require_scope

router = APIRouter(tags=["Conversations"])
_EXPORT_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Exported conversation data",
        "content": {
            "application/x-ndjson": {"schema": {"type": "string", "format": "binary"}}
        },
    }
}


def get_service(request: Request) -> ConversationService:
    return request.app.state.services.conversations


async def require_data_scope(request: Request) -> AuthContext:
    auth = await require_scope(request, "data")
    user_id = request.query_params.get("user_id")
    conversation_id = request.path_params.get("conversation_id")
    if user_id and conversation_id:
        resource = object_resource(
            "conversation", user_id, conversation_id, config_id=None
        )
    else:
        resource = Resource.named("conversation", "collection")
    await require_resource_action(
        request,
        auth,
        action="data.manage",
        resource=resource,
    )
    return auth


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


@router.post("/conversations/export", responses=_EXPORT_RESPONSE)
async def export_conversations(
    payload: ConversationExportRequest,
    request: Request,
    auth: AuthContext = Depends(require_data_scope),
    service: ConversationService = Depends(get_service),
):
    # Exporting arbitrary users' conversations is a separate high-risk
    # capability.  Keep the normal ``data`` scope for discovery and edits,
    # but require an explicit control-plane authorization for this endpoint.
    await require_resource_action(
        request,
        auth,
        action="data.export_all",
        resource=Resource.named("conversation", "export"),
    )
    return await _export_conversations(_model_dict(payload), service)


@router.post("/conversations/batch-delete")
async def batch_delete_conversations(
    payload: ConversationBatchDeleteRequest,
    request: Request,
    auth: AuthContext = Depends(require_data_scope),
    service: ConversationService = Depends(get_service),
):
    for conversation in payload.conversations:
        user_id = conversation.user_id
        conversation_id = conversation.cid
        if user_id and conversation_id:
            await require_resource_action(
                request,
                auth,
                action="data.manage",
                resource=object_resource("conversation", user_id, conversation_id),
            )
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
    if body_user_id != user_id:
        raise ApiError("user_id does not match query parameter", status_code=400)
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
    if body_user_id != user_id:
        raise ApiError("user_id does not match query parameter", status_code=400)
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
