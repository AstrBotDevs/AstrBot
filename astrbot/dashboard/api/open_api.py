from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, WebSocket
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from astrbot.dashboard.responses import ApiError, error, ok
from astrbot.dashboard.schemas import ImMessageRequest, OpenApiChatRequest
from astrbot.dashboard.services.chat_service import (
    ChatService,
    ChatServiceError,
    extract_web_search_refs,
)
from astrbot.dashboard.services.open_api_service import (
    OpenApiService,
    OpenApiServiceError,
    OpenApiWebSocketChatBridge,
)

from .auth import AuthContext, require_scope
from .multipart import UploadFileAdapter

router = APIRouter(tags=["Open API"])


async def require_im_scope(request: Request) -> AuthContext:
    return await require_scope(request, "im")


async def require_chat_scope(request: Request) -> AuthContext:
    return await require_scope(request, "chat")


async def require_config_scope(request: Request) -> AuthContext:
    return await require_scope(request, "config")


async def require_file_scope(request: Request) -> AuthContext:
    return await require_scope(request, "file")


def get_service(request: Request) -> OpenApiService:
    return request.app.state.services.open_api


def get_chat_service(request: Request) -> ChatService:
    return request.app.state.services.chat


def _model_dict(payload) -> dict[str, Any]:
    if payload is None:
        return {}
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_unset=True, exclude_none=False)
    return payload if isinstance(payload, dict) else {}


def _open_api_error(message: str) -> JSONResponse:
    return JSONResponse(error(message))


def _get_chat_config_list(service: OpenApiService) -> list[dict]:
    return service.get_chat_config_list()


async def _build_streaming_chat_response(
    chat_service: ChatService,
    username: str,
    post_data: dict[str, Any],
) -> StreamingResponse | JSONResponse:
    try:
        stream = await chat_service.build_chat_stream(username, post_data)
    except ChatServiceError as exc:
        return _open_api_error(str(exc))

    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Transfer-Encoding": "chunked",
            "Connection": "keep-alive",
        },
    )


async def _open_api_chat_response(
    post_data: dict[str, Any],
    auth: AuthContext,
    open_api_service: OpenApiService,
    chat_service: ChatService,
) -> StreamingResponse | JSONResponse:
    if auth.via != "api_key":
        return await _build_streaming_chat_response(
            chat_service,
            auth.username,
            post_data,
        )

    try:
        (
            effective_username,
            session_id,
            config_id,
        ) = await open_api_service.prepare_chat_send(
            post_data,
            _get_chat_config_list(open_api_service),
        )
    except OpenApiServiceError as exc:
        return _open_api_error(str(exc))

    config_err = await open_api_service.update_session_config_route(
        username=effective_username,
        session_id=session_id,
        config_id=config_id,
    )
    if config_err:
        return _open_api_error(config_err)

    return await _build_streaming_chat_response(
        chat_service,
        effective_username,
        post_data,
    )


async def _insert_webchat_user_message(
    service: OpenApiService,
    session_id: str,
    effective_username: str,
    message_parts: list,
) -> None:
    await service.insert_webchat_user_message(
        session_id=session_id,
        effective_username=effective_username,
        message_parts=message_parts,
    )


def _build_chat_ws_bridge(
    open_api_service: OpenApiService,
    chat_service: ChatService,
) -> OpenApiWebSocketChatBridge:
    return OpenApiWebSocketChatBridge(
        build_user_message_parts=lambda message: chat_service.build_user_message_parts(
            message if isinstance(message, str | list) else str(message),
        ),
        create_attachment_from_file=chat_service.create_attachment_from_file,
        extract_web_search_refs=extract_web_search_refs,
        insert_user_message=lambda session_id, effective_username, message_parts: (
            _insert_webchat_user_message(
                open_api_service,
                session_id,
                effective_username,
                message_parts,
            )
        ),
        save_bot_message=chat_service.save_bot_message,
    )


def _extract_ws_api_key(websocket: WebSocket) -> str | None:
    if key := websocket.query_params.get("api_key"):
        return key.strip()
    if key := websocket.query_params.get("key"):
        return key.strip()
    if key := websocket.headers.get("X-API-Key"):
        return key.strip()

    auth_header = websocket.headers.get("Authorization", "").strip()
    if auth_header.startswith("Bearer "):
        return auth_header.removeprefix("Bearer ").strip()
    if auth_header.startswith("ApiKey "):
        return auth_header.removeprefix("ApiKey ").strip()
    return None


@router.post("/chat")
async def chat(
    payload: OpenApiChatRequest,
    auth: AuthContext = Depends(require_chat_scope),
    service: OpenApiService = Depends(get_service),
    chat_service: ChatService = Depends(get_chat_service),
):
    return await _open_api_chat_response(
        _model_dict(payload),
        auth,
        service,
        chat_service,
    )


@router.get("/chat/sessions")
async def chat_sessions(
    request: Request,
    auth: AuthContext = Depends(require_chat_scope),
    service: OpenApiService = Depends(get_service),
    chat_service: ChatService = Depends(get_chat_service),
):
    if auth.via != "api_key":
        try:
            return ok(
                await chat_service.get_sessions(
                    auth.username,
                    request.query_params.get("platform_id"),
                )
            )
        except ChatServiceError as exc:
            return error(str(exc))

    try:
        return ok(
            await service.get_chat_sessions_from_dashboard_query(
                username=request.query_params.get("username"),
                page=request.query_params.get("page", 1),
                page_size=request.query_params.get("page_size", 20),
                platform_id=request.query_params.get("platform_id"),
            )
        )
    except OpenApiServiceError as exc:
        return error(str(exc))


@router.get("/configs", include_in_schema=False)
async def get_chat_configs(
    _auth: AuthContext = Depends(require_config_scope),
    service: OpenApiService = Depends(get_service),
):
    return ok(service.get_chat_configs())


@router.post(
    "/file",
    summary="Upload a file",
    operation_id="uploadOpenApiFile",
    openapi_extra={"x-astrbot-scope": "file"},
)
async def upload_open_api_file(
    file: UploadFile = File(...),
    _auth: AuthContext = Depends(require_file_scope),
    chat_service: ChatService = Depends(get_chat_service),
):
    try:
        return ok(await chat_service.save_uploaded_file(UploadFileAdapter(file)))
    except ChatServiceError as exc:
        return error(str(exc))


@router.get(
    "/file",
    summary="Download an uploaded file by attachment ID",
    operation_id="downloadOpenApiFile",
    responses={
        200: {
            "description": "File content or an error envelope",
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
        },
    },
    openapi_extra={"x-astrbot-scope": "file"},
)
async def get_open_api_file(
    attachment_id: str = Query(...),
    _auth: AuthContext = Depends(require_file_scope),
    chat_service: ChatService = Depends(get_chat_service),
):
    try:
        file_path, mimetype = await chat_service.resolve_attachment_file(attachment_id)
        return FileResponse(file_path, media_type=mimetype)
    except ChatServiceError as exc:
        return _open_api_error(str(exc))
    except (FileNotFoundError, OSError):
        return _open_api_error("File access error")


@router.websocket("/chat/ws")
async def chat_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    service: OpenApiService = websocket.app.state.services.open_api
    chat_service: ChatService = websocket.app.state.services.chat

    async def close_ws(code: int, reason: str) -> None:
        await websocket.close(code=code, reason=reason)

    await service.run_chat_websocket(
        raw_api_key=_extract_ws_api_key(websocket),
        receive_json=websocket.receive_json,
        send_json=websocket.send_json,
        close=close_ws,
        conf_list=_get_chat_config_list(service),
        chat_bridge=_build_chat_ws_bridge(service, chat_service),
    )


@router.post("/im/messages")
async def send_im_message(
    payload: ImMessageRequest,
    _auth: AuthContext = Depends(require_im_scope),
    service: OpenApiService = Depends(get_service),
):
    body = _model_dict(payload)
    try:
        await service.send_message(body)
    except OpenApiServiceError as exc:
        raise ApiError(str(exc)) from exc

    return ok()


@router.post("/im/message", include_in_schema=False)
async def send_im_message_alias(
    payload: ImMessageRequest,
    auth: AuthContext = Depends(require_im_scope),
    service: OpenApiService = Depends(get_service),
):
    return await send_im_message(payload, auth, service)


@router.get("/im/bots")
async def list_im_bots(
    _request: Request,
    _auth: AuthContext = Depends(require_im_scope),
    service: OpenApiService = Depends(get_service),
):
    return ok(service.get_bots())
