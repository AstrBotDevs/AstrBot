from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.responses import error, ok
from astrbot.dashboard.schemas import (
    ChatMessagePatchRequest,
    ChatMessageRegenerateRequest,
    ChatSessionBatchDeleteRequest,
    ChatSessionPatchRequest,
    ChatThreadCreateRequest,
    ChatThreadMessageRequest,
)
from astrbot.dashboard.services.chat_service import (
    ChatService,
    ChatServiceError,
)

from .auth import AuthContext, require_scope

router = APIRouter(tags=["Chat"])
_SSE_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Server-sent chat stream or an error envelope",
        "content": {"text/event-stream": {"schema": {"type": "string"}}},
    }
}


def get_service(request: Request) -> ChatService:
    return request.app.state.services.chat


async def require_chat_scope(request: Request) -> AuthContext:
    return await require_scope(request, "chat")


async def _json_or_empty(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


async def _json_or_none(request: Request) -> dict[str, Any] | None:
    try:
        data = await request.json()
    except Exception:
        return None
    return data if isinstance(data, dict) else None


async def _json_body(request: Request):
    try:
        return await request.json()
    except Exception:
        return None


def _model_dict(payload) -> dict[str, Any]:
    return payload.model_dump(exclude_unset=True, exclude_none=False)


async def _run(operation):
    try:
        result = await run_maybe_async(operation)
        return ok(result)
    except ChatServiceError as exc:
        return error(str(exc))


def _file_response(file_path: str, mimetype: str | None):
    if mimetype:
        return FileResponse(file_path, media_type=mimetype)
    return FileResponse(file_path)


async def _send_chat(
    *,
    request: Request,
    username: str,
    auth: AuthContext,
    service: ChatService,
    payload: dict[str, Any] | None = None,
):
    post_data = payload if payload is not None else await _json_or_none(request)
    if post_data is None:
        return JSONResponse(error("Missing JSON body"))

    try:
        dashboard_principal = None
        if auth.via == "jwt" and auth.account_id and auth.sid:
            dashboard_principal = {
                "account_id": auth.account_id,
                "sid": auth.sid,
                "username": auth.username,
                "auth_strength": auth.auth_strength,
            }
        stream = await service.build_chat_stream(
            username,
            post_data,
            dashboard_principal=dashboard_principal,
        )
    except ChatServiceError as exc:
        return JSONResponse(error(str(exc)))

    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Transfer-Encoding": "chunked",
            "Connection": "keep-alive",
        },
    )


@router.get("/chat/sessions/new")
async def create_chat_session(
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatService = Depends(get_service),
):
    return await _run(
        lambda: service.new_session(
            auth.username,
            request.query_params.get("platform_id") or "webchat",
        )
    )


@router.post("/chat/sessions/batch-delete")
async def batch_delete_chat_sessions(
    payload: ChatSessionBatchDeleteRequest,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatService = Depends(get_service),
):
    return await _run(
        lambda: service.batch_delete_sessions(auth.username, payload.session_ids)
    )


@router.get("/chat/sessions/{session_id}")
async def get_chat_session(
    session_id: str,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatService = Depends(get_service),
):
    return await _run(lambda: service.get_session(auth.username, session_id))


@router.patch("/chat/sessions/{session_id}")
async def update_chat_session(
    session_id: str,
    payload: ChatSessionPatchRequest,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatService = Depends(get_service),
):
    return await _run(
        lambda: service.update_session_display_name(
            auth.username,
            session_id,
            payload.display_name,
        )
    )


@router.delete("/chat/sessions/{session_id}")
async def delete_chat_session(
    session_id: str,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatService = Depends(get_service),
):
    return await _run(lambda: service.delete_webchat_session(auth.username, session_id))


@router.post("/chat/sessions/{session_id}/stop")
async def stop_chat_session(
    session_id: str,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatService = Depends(get_service),
):
    return await _run(lambda: service.stop_session(auth.username, session_id))


@router.get("/chat/runs/{run_id}/stream", responses=_SSE_RESPONSE)
async def resume_chat_run(
    run_id: str,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatService = Depends(get_service),
):
    try:
        stream = await service.build_chat_run_stream(auth.username, run_id)
    except ChatServiceError:
        return JSONResponse(error("Chat run is unavailable"))

    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Transfer-Encoding": "chunked",
            "Connection": "keep-alive",
        },
    )


@router.patch("/chat/sessions/{session_id}/messages/{message_id}")
async def update_chat_message(
    session_id: str,
    message_id: str,
    payload: ChatMessagePatchRequest,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatService = Depends(get_service),
):
    return await _run(
        lambda: service.update_message(
            auth.username,
            {
                "session_id": session_id,
                "message_id": message_id,
                **_model_dict(payload),
            },
        )
    )


@router.post(
    "/chat/sessions/{session_id}/messages/{message_id}/regenerate",
    responses=_SSE_RESPONSE,
)
async def regenerate_chat_message(
    session_id: str,
    message_id: str,
    request: Request,
    payload: ChatMessageRegenerateRequest | None = None,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatService = Depends(get_service),
):
    body = _model_dict(payload) if payload is not None else {}
    try:
        chat_payload = await service.prepare_regenerate_message_payload(
            auth.username,
            {"session_id": session_id, "message_id": message_id, **body},
        )
    except ChatServiceError as exc:
        return JSONResponse(error(str(exc)))
    return await _send_chat(
        request=request,
        username=auth.username,
        auth=auth,
        service=service,
        payload=chat_payload,
    )


@router.get("/chat/configs")
async def chat_configs(
    request: Request,
    _auth: AuthContext = Depends(require_chat_scope),
):
    return ok(request.app.state.services.config_profiles.list_profiles())


@router.post("/chat/threads")
async def create_chat_thread(
    payload: ChatThreadCreateRequest,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatService = Depends(get_service),
):
    return await _run(
        lambda: service.create_thread(auth.username, _model_dict(payload))
    )


@router.get("/chat/threads/{thread_id}")
async def get_chat_thread(
    thread_id: str,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatService = Depends(get_service),
):
    return await _run(lambda: service.get_thread(auth.username, thread_id))


@router.delete("/chat/threads/{thread_id}")
async def delete_chat_thread(
    thread_id: str,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatService = Depends(get_service),
):
    return await _run(lambda: service.delete_thread(auth.username, thread_id))


@router.post("/chat/threads/{thread_id}/messages", responses=_SSE_RESPONSE)
async def send_chat_thread_message(
    thread_id: str,
    request: Request,
    payload: ChatThreadMessageRequest,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatService = Depends(get_service),
):
    try:
        chat_payload = await service.prepare_thread_chat_payload(
            auth.username,
            {"thread_id": thread_id, **_model_dict(payload)},
        )
    except ChatServiceError as exc:
        return JSONResponse(error(str(exc)))
    return await _send_chat(
        request=request,
        username=auth.username,
        auth=auth,
        service=service,
        payload=chat_payload,
    )
