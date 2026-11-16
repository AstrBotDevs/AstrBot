from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from astrbot.core.chatui import ViewActionRequest, ViewError, view_store
from astrbot.core.message.components import UIInteraction, ViewContext
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
    MAX_UPLOAD_FILE_SIZE_BYTES,
    MAX_UPLOAD_FILE_SIZE_MB,
    ChatService,
    ChatServiceError,
)

from .auth import AuthContext, ScopeDependency, require_dashboard_user
from .multipart import single_upload

router = APIRouter(tags=["Chat"])
legacy_router = APIRouter(
    prefix="/api/chat",
    tags=["Dashboard Chat"],
    include_in_schema=False,
)


def get_service(request: Request) -> ChatService:
    return request.app.state.services.chat


require_chat_scope = ScopeDependency("chat")

# HTTP responses use fixed public text, never the exception's diagnostic message.
VIEW_ERROR_MESSAGES = {
    "FORBIDDEN": "This view is not accessible.",
    "VIEW_UNAVAILABLE": "This view is unavailable.",
    "ACTION_NOT_ALLOWED": "This action is not declared by the view.",
    "INVALID_INPUT": "The view action input is invalid.",
    "REVISION_CONFLICT": "The view has changed. Review it and try again.",
    "ACTION_IN_PROGRESS": "Another action is still pending.",
    "ACTION_OUTCOME_UNKNOWN": "The action has no recorded outcome yet.",
}


@router.get("/chat/views/{view_id}")
async def get_chat_view(
    view_id: str,
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatService = Depends(get_service),
):
    """Return an authorized card snapshot and scoped frontend resources."""
    try:
        record, plugin, spec, entry = await service.get_chat_view(
            auth.username, view_id
        )
        pages = request.app.state.services.plugin_pages
        token = pages.issue_plugin_page_asset_token(
            plugin_name=plugin.name,
            view_name=spec.name,
            username=auth.username,
            locale="en-US",
        )
        if not token:
            raise ViewError("VIEW_UNAVAILABLE", "View resources are unavailable.")
        return ok(
            {
                "id": view_id,
                "name": spec.name,
                "data": record["data"],
                "revision": record["revision"],
                "text": record["text"],
                "context": {
                    "pluginName": plugin.name,
                    "displayName": plugin.display_name or plugin.name,
                    "pageName": spec.name,
                    "pageTitle": spec.name,
                    "i18n": plugin.i18n or {},
                },
                "html": await asyncio.to_thread(entry.read_text, encoding="utf-8"),
                "base_url": pages.build_plugin_page_view_content_path(
                    plugin.name, spec.name, token
                ),
            }
        )
    except ViewError as exc:
        return JSONResponse(
            {
                "code": exc.code,
                "message": VIEW_ERROR_MESSAGES.get(
                    exc.code, "The view request could not be completed."
                ),
            },
            status_code=403 if exc.code == "FORBIDDEN" else 404,
        )


@router.post("/chat/views/{view_id}/actions")
async def run_chat_view_action(
    view_id: str,
    payload: ViewActionRequest,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatService = Depends(get_service),
):
    """Submit a view action to the authenticated message event pipeline."""
    try:
        record, _, spec, _ = await service.get_chat_view(auth.username, view_id)
        if payload.action_id not in spec.actions:
            raise ViewError(
                "ACTION_NOT_ALLOWED", "This action is not declared by the view."
            )
        previous = await asyncio.to_thread(view_store.begin, view_id, payload)
        if previous is not None:
            return JSONResponse(previous)
        # The reservation excludes competing callbacks; now read its snapshot.
        record = await asyncio.to_thread(view_store.get, view_id)
        interaction = UIInteraction(
            action_id=payload.action_id,
            interaction_id=payload.interaction_id,
            data=payload.data,
            source_message_id=record["message_id"],
            view=ViewContext(
                **{
                    key: record[key]
                    for key in ("id", "name", "version", "revision", "data")
                }
            ),
        )
        post_data = {
            "session_id": record["session_id"],
            "message": [{"type": "plain", "text": payload.action_id}],
            "_skip_user_history": True,
            "_platform_history_id": record["platform"],
            "_api_key_allow_admin_role": auth.via != "api_key"
            or "chat:admin" in auth.scopes,
        }
        if record["platform"] == "webchat_thread":
            thread = await service.db.get_webchat_thread_by_id(record["session_id"])
            post_data["_thread_selected_text"] = thread.selected_text
        try:
            stream = await service.build_chat_stream(
                auth.username,
                post_data,
                ui_interaction=interaction,
                ui_plugin_module=record["module"],
            )
        except BaseException:
            await asyncio.to_thread(
                view_store.finish,
                view_id,
                payload.interaction_id,
                error={
                    "code": "ACTION_FAILED",
                    "message": "The action could not be dispatched.",
                },
            )
            raise
        return StreamingResponse(
            stream,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )
    except ViewError as exc:
        response = {
            "code": exc.code,
            "message": VIEW_ERROR_MESSAGES.get(
                exc.code, "The view request could not be completed."
            ),
        }
        if exc.code == "REVISION_CONFLICT":
            current = await asyncio.to_thread(view_store.get, view_id)
            response["snapshot"] = {
                "data": current["data"],
                "revision": current["revision"],
            }
        return JSONResponse(
            response,
            status_code=409
            if exc.code
            in {"REVISION_CONFLICT", "ACTION_IN_PROGRESS", "ACTION_OUTCOME_UNKNOWN"}
            else 403,
        )


@router.get("/chat/views/{view_id}/actions/{interaction_id}")
async def get_chat_view_action(
    view_id: str,
    interaction_id: str,
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatService = Depends(get_service),
):
    """Read an accepted action without executing plugin code again."""
    try:
        await service.get_chat_view(auth.username, view_id)
        with view_store.connect() as db:
            row = db.execute(
                "SELECT result,started FROM actions WHERE view_id=? AND id=?",
                (view_id, interaction_id),
            ).fetchone()
        if not row:
            return JSONResponse(
                {"code": "ACTION_NOT_FOUND", "message": "The action was not accepted."},
                status_code=404,
            )
        if row["result"]:
            return JSONResponse(json.loads(row["result"]))
        return JSONResponse(
            {
                "code": "ACTION_IN_PROGRESS"
                if time.time() - row["started"] < 180
                else "ACTION_OUTCOME_UNKNOWN",
                "message": "The action has no recorded outcome yet.",
            },
            status_code=409,
        )
    except ViewError as exc:
        return JSONResponse(
            {
                "code": exc.code,
                "message": VIEW_ERROR_MESSAGES.get(
                    exc.code, "The view request could not be completed."
                ),
            },
            status_code=403,
        )


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
    service: ChatService,
    payload: dict[str, Any] | None = None,
):
    post_data = payload if payload is not None else await _json_or_none(request)
    if post_data is None:
        return JSONResponse(error("Missing JSON body"))

    try:
        stream = await service.build_chat_stream(username, post_data)
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


@router.post("/chat/transcriptions")
async def transcribe_chat_audio(
    file: UploadFile = File(...),
    provider_id: str = Form(default=""),
    _username: str = Depends(require_dashboard_user),
    service: ChatService = Depends(get_service),
):
    try:
        return await _run(lambda: service.transcribe_audio(file, provider_id))
    finally:
        await file.close()


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
        lambda: service.batch_delete_sessions_from_dashboard_payload(
            auth.username,
            _model_dict(payload),
        )
    )


@router.get("/chat/sessions/{session_id}")
async def get_chat_session(
    session_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=1000, ge=1, le=1000),
    auth: AuthContext = Depends(require_chat_scope),
    service: ChatService = Depends(get_service),
):
    return await _run(
        lambda: service.get_session(
            auth.username,
            session_id,
            page=page,
            page_size=page_size,
        )
    )


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


@router.get("/chat/runs/{run_id}/stream")
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


@router.post("/chat/sessions/{session_id}/messages/{message_id}/regenerate")
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


@router.post("/chat/threads/{thread_id}/messages")
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
        service=service,
        payload=chat_payload,
    )


@legacy_router.post("/send")
async def dashboard_send_chat(
    request: Request,
    username: str = Depends(require_dashboard_user),
    service: ChatService = Depends(get_service),
):
    return await _send_chat(request=request, username=username, service=service)


@legacy_router.get("/new_session")
async def dashboard_new_session(
    request: Request,
    username: str = Depends(require_dashboard_user),
    service: ChatService = Depends(get_service),
):
    return await _run(
        lambda: service.new_session(
            username,
            request.query_params.get("platform_id") or "webchat",
        )
    )


@legacy_router.get("/sessions")
async def dashboard_get_sessions(
    request: Request,
    username: str = Depends(require_dashboard_user),
    service: ChatService = Depends(get_service),
):
    return await _run(
        lambda: service.get_sessions(username, request.query_params.get("platform_id"))
    )


@legacy_router.get("/get_session")
async def dashboard_get_session(
    request: Request,
    username: str = Depends(require_dashboard_user),
    service: ChatService = Depends(get_service),
):
    return await _run(
        lambda: service.get_session_from_dashboard_query(
            username,
            request.query_params.get("session_id"),
        )
    )


@legacy_router.post("/stop")
async def dashboard_stop_session(
    request: Request,
    username: str = Depends(require_dashboard_user),
    service: ChatService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(
        lambda: service.stop_session_from_dashboard_payload(username, body)
    )


@legacy_router.get("/delete_session")
async def dashboard_delete_session(
    request: Request,
    username: str = Depends(require_dashboard_user),
    service: ChatService = Depends(get_service),
):
    return await _run(
        lambda: service.delete_webchat_session_from_dashboard_query(
            username,
            request.query_params.get("session_id"),
        )
    )


@legacy_router.post("/batch_delete_sessions")
async def dashboard_batch_delete_sessions(
    request: Request,
    username: str = Depends(require_dashboard_user),
    service: ChatService = Depends(get_service),
):
    body = await _json_body(request)
    return await _run(
        lambda: service.batch_delete_sessions_from_dashboard_payload(username, body)
    )


@legacy_router.post("/update_session_display_name")
async def dashboard_update_session_display_name(
    request: Request,
    username: str = Depends(require_dashboard_user),
    service: ChatService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(
        lambda: service.update_session_display_name_from_dashboard_payload(
            username,
            body,
        )
    )


@legacy_router.post("/message/edit")
async def dashboard_update_message(
    request: Request,
    username: str = Depends(require_dashboard_user),
    service: ChatService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.update_message(username, body))


@legacy_router.post("/message/regenerate")
async def dashboard_regenerate_message(
    request: Request,
    username: str = Depends(require_dashboard_user),
    service: ChatService = Depends(get_service),
):
    try:
        payload = (
            await service.prepare_regenerate_message_payload_from_dashboard_payload(
                username,
                await _json_or_empty(request),
            )
        )
    except ChatServiceError as exc:
        return JSONResponse(error(str(exc)))
    return await _send_chat(
        request=request,
        username=username,
        service=service,
        payload=payload,
    )


@legacy_router.post("/thread/create")
async def dashboard_create_thread(
    request: Request,
    username: str = Depends(require_dashboard_user),
    service: ChatService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.create_thread(username, body))


@legacy_router.get("/thread/get")
async def dashboard_get_thread(
    request: Request,
    username: str = Depends(require_dashboard_user),
    service: ChatService = Depends(get_service),
):
    return await _run(
        lambda: service.get_thread_from_dashboard_query(
            username,
            request.query_params.get("thread_id"),
        )
    )


@legacy_router.post("/thread/send")
async def dashboard_send_thread_message(
    request: Request,
    username: str = Depends(require_dashboard_user),
    service: ChatService = Depends(get_service),
):
    try:
        payload = await service.prepare_thread_chat_payload_from_dashboard_payload(
            username,
            await _json_or_empty(request),
        )
    except ChatServiceError as exc:
        return JSONResponse(error(str(exc)))
    return await _send_chat(
        request=request,
        username=username,
        service=service,
        payload=payload,
    )


@legacy_router.post("/thread/delete")
async def dashboard_delete_thread(
    request: Request,
    username: str = Depends(require_dashboard_user),
    service: ChatService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(
        lambda: service.delete_thread_from_dashboard_payload(username, body)
    )


@legacy_router.get("/get_file")
async def dashboard_get_file(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: ChatService = Depends(get_service),
):
    try:
        file_path, mimetype = await service.resolve_webchat_file_from_dashboard_query(
            request.query_params.get("filename")
        )
        return _file_response(file_path, mimetype)
    except ChatServiceError as exc:
        return JSONResponse(error(str(exc)))
    except (FileNotFoundError, OSError):
        return JSONResponse(error("File access error"))


@legacy_router.get("/get_attachment")
async def dashboard_get_attachment(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: ChatService = Depends(get_service),
):
    try:
        (
            file_path,
            mimetype,
        ) = await service.resolve_attachment_file_from_dashboard_query(
            request.query_params.get("attachment_id")
        )
        return _file_response(file_path, mimetype)
    except ChatServiceError as exc:
        return JSONResponse(error(str(exc)))
    except (FileNotFoundError, OSError):
        return JSONResponse(error("File access error"))


@legacy_router.post("/post_file")
async def dashboard_post_file(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: ChatService = Depends(get_service),
):
    try:
        content_length = int(request.headers.get("content-length") or 0)
        if content_length > MAX_UPLOAD_FILE_SIZE_BYTES:
            raise ChatServiceError(
                f"File too large (limit {MAX_UPLOAD_FILE_SIZE_MB} MB)"
            )
        upload = await single_upload(request)
        if upload is None:
            raise ChatServiceError("Missing key: file")
        return ok(await service.save_uploaded_file(upload))
    except ChatServiceError as exc:
        return error(str(exc))
