import asyncio
import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import astrbot.dashboard.services.open_api_service as open_api_service_module
from astrbot.core.platform.send_result import PlatformSendResult
from astrbot.core.webchat.queue_manager import WebChatQueueManager
from astrbot.core.webchat.run_coordinator import WebChatRunCoordinator
from astrbot.dashboard.services.open_api_service import (
    OpenApiKeyAuthContext,
    OpenApiService,
    OpenApiServiceError,
    OpenApiWebSocketChatBridge,
)

_SENSITIVE_INTERNAL_ERROR = (
    "api_key=ws-secret Bearer ws-token password=ws-password "
    "https://internal.example.test/ws C:\\private\\ws-secret.txt"
)
_SENSITIVE_FRAGMENTS = (
    "ws-secret",
    "ws-token",
    "ws-password",
    "internal.example.test",
    "C:\\private\\ws-secret.txt",
)


def _assert_no_sensitive_fragments(*texts: str) -> None:
    for text in texts:
        for fragment in _SENSITIVE_FRAGMENTS:
            assert fragment not in text


def _service() -> OpenApiService:
    authorization = SimpleNamespace(
        authorize=AsyncMock(return_value=SimpleNamespace(allowed=True))
    )
    return OpenApiService(
        SimpleNamespace(
            get_attachment_by_id=lambda _attachment_id: None,
        ),
        platform_manager=SimpleNamespace(send_to_session=None),
        astrbot_config_mgr=SimpleNamespace(get_conf_list=lambda: []),
        umop_config_router=SimpleNamespace(),
        astrbot_config={"platform": []},
        platform_message_history_manager=SimpleNamespace(),
        webchat_run_coordinator=WebChatRunCoordinator(WebChatQueueManager()),
        authorization=authorization,
    )


def _bridge() -> OpenApiWebSocketChatBridge:
    async def build_user_message_parts(_message):
        return []

    async def create_attachment_from_file(_filename, _attach_type):
        return None

    async def insert_user_message(_session_id, _effective_username, _message_parts):
        pass

    async def save_bot_message(_session_id, _message_parts, _agent_stats, _refs):
        return None

    return OpenApiWebSocketChatBridge(
        build_user_message_parts=build_user_message_parts,
        create_attachment_from_file=create_attachment_from_file,
        extract_web_search_refs=lambda _text, _parts: {},
        insert_user_message=insert_user_message,
        save_bot_message=save_bot_message,
    )


@pytest.mark.asyncio
async def test_run_chat_websocket_closes_when_api_key_is_invalid(monkeypatch):
    service = _service()
    sent: list[dict] = []
    closed: list[tuple[int, str]] = []

    async def authenticate_api_key(_raw_key):
        return None, "Invalid API key"

    monkeypatch.setattr(service, "authenticate_api_key", authenticate_api_key)

    async def receive_json():
        raise AssertionError("receive_json should not be called")

    async def send_json(payload: dict) -> None:
        sent.append(payload)

    async def close(code: int, reason: str) -> None:
        closed.append((code, reason))

    await service.run_chat_websocket(
        raw_api_key="bad",
        receive_json=receive_json,
        send_json=send_json,
        close=close,
        conf_list=[],
        chat_bridge=_bridge(),
    )

    assert sent == [
        {"type": "error", "code": "UNAUTHORIZED", "data": "Invalid API key"}
    ]
    assert closed == [(1008, "Invalid API key")]


@pytest.mark.asyncio
async def test_run_chat_websocket_fails_closed_without_authorization_service(
    monkeypatch,
):
    service = _service()
    service.authorization = None
    sent: list[dict] = []
    closed: list[tuple[int, str]] = []

    async def authenticate_api_key(_raw_key):
        return OpenApiKeyAuthContext("test-key", ("chat",)), None

    monkeypatch.setattr(service, "authenticate_api_key", authenticate_api_key)

    async def send_json(payload: dict) -> None:
        sent.append(payload)

    async def close(code: int, reason: str) -> None:
        closed.append((code, reason))

    await service.run_chat_websocket(
        raw_api_key="good",
        receive_json=AsyncMock(),
        send_json=send_json,
        close=close,
        conf_list=[],
        chat_bridge=_bridge(),
    )

    assert sent == [
        {
            "type": "error",
            "code": "PROCESSING_ERROR",
            "data": "Authorization unavailable",
        }
    ]
    assert closed == [(1011, "Authorization unavailable")]


@pytest.mark.asyncio
async def test_run_chat_websocket_hides_authentication_failures(monkeypatch, caplog):
    service = _service()
    sent: list[dict] = []
    closed: list[tuple[int, str]] = []

    async def authenticate_api_key(_raw_key):
        raise RuntimeError(_SENSITIVE_INTERNAL_ERROR)

    monkeypatch.setattr(service, "authenticate_api_key", authenticate_api_key)

    async def receive_json():
        raise AssertionError("receive_json should not be called")

    async def send_json(payload: dict) -> None:
        sent.append(payload)

    async def close(code: int, reason: str) -> None:
        closed.append((code, reason))

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        await service.run_chat_websocket(
            raw_api_key="key",
            receive_json=receive_json,
            send_json=send_json,
            close=close,
            conf_list=[],
            chat_bridge=_bridge(),
        )

    assert sent == [
        {
            "type": "error",
            "code": "PROCESSING_ERROR",
            "data": "Internal server error",
        }
    ]
    assert closed == [(1011, "Internal server error")]
    _assert_no_sensitive_fragments(caplog.text)


@pytest.mark.asyncio
async def test_run_chat_websocket_handles_control_messages(monkeypatch):
    service = _service()
    messages = iter(
        [
            ["not", "an", "object"],
            {"t": "ping"},
            {"t": "unknown"},
            {"t": "send", "message": "hello"},
        ]
    )
    sent: list[dict] = []
    handled: list[dict] = []

    async def authenticate_api_key(_raw_key):
        return OpenApiKeyAuthContext("test-key", ("chat",)), None

    async def handle_chat_ws_send(**kwargs):
        handled.append(kwargs["post_data"])

    monkeypatch.setattr(service, "authenticate_api_key", authenticate_api_key)
    monkeypatch.setattr(service, "handle_chat_ws_send", handle_chat_ws_send)

    async def receive_json():
        try:
            return next(messages)
        except StopIteration as exc:
            raise RuntimeError("disconnect") from exc

    async def send_json(payload: dict) -> None:
        sent.append(payload)

    async def close(_code: int, _reason: str) -> None:
        raise AssertionError("close should not be called")

    await service.run_chat_websocket(
        raw_api_key="good",
        receive_json=receive_json,
        send_json=send_json,
        close=close,
        conf_list=[],
        chat_bridge=_bridge(),
    )

    assert sent == [
        {
            "type": "error",
            "code": "INVALID_MESSAGE",
            "data": "message must be an object",
        },
        {"type": "pong"},
        {
            "type": "error",
            "code": "INVALID_MESSAGE",
            "data": "Unsupported message type: unknown",
        },
    ]
    assert handled == [{"t": "send", "message": "hello"}]


@pytest.mark.asyncio
async def test_handle_chat_ws_send_reduces_queue_results_and_persists_native_refs(
    monkeypatch,
):
    service = _service()
    back_queue = asyncio.Queue()
    chat_queue = MagicMock()
    chat_queue.put = AsyncMock()
    service.prepare_chat_send = AsyncMock(return_value=("alice", "session-1", None))
    service.update_session_config_route = AsyncMock(return_value=None)
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "get_or_create_back_queue",
        lambda *_args: back_queue,
    )
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "get_or_create_queue",
        lambda *_args: chat_queue,
    )
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "remove_back_queue",
        MagicMock(),
    )

    saved = []

    async def build_user_message_parts(_message):
        return [{"type": "plain", "text": "question"}]

    async def create_attachment(filename, attach_type, display_name=None):
        assert (filename, attach_type, display_name) == (
            "stored.pdf",
            "file",
            "report.pdf",
        )
        return {"type": "file", "attachment_id": "attachment-1"}

    async def insert_user_message(*_args):
        return None

    async def save_bot_message(*args):
        saved.append(args)
        return SimpleNamespace(id=99, created_at=datetime.now(UTC))

    bridge = OpenApiWebSocketChatBridge(
        build_user_message_parts=build_user_message_parts,
        create_attachment_from_file=create_attachment,
        extract_web_search_refs=lambda *_args: {
            "used": [{"url": "https://example.com", "title": "Tool source"}]
        },
        insert_user_message=insert_user_message,
        save_bot_message=save_bot_message,
    )
    await back_queue.put({"message_id": "wrong", "type": "plain", "data": "ignored"})
    await back_queue.put(
        {
            "message_id": "message-1",
            "type": "plain",
            "data": '{"id":"tool-1","name":"search"}',
            "streaming": True,
            "chain_type": "tool_call",
        }
    )
    await back_queue.put(
        {
            "message_id": "message-1",
            "type": "agent_stats",
            "data": '{"latency": 3}',
            "chain_type": "agent_stats",
        }
    )
    await back_queue.put(
        {
            "message_id": "message-1",
            "type": "refs",
            "data": {"used": [{"url": "https://example.com", "snippet": "Native"}]},
        }
    )
    await back_queue.put(
        {
            "message_id": "message-1",
            "type": "plain",
            "data": "answer",
            "streaming": True,
        }
    )
    await back_queue.put(
        {
            "message_id": "message-1",
            "type": "file",
            "data": "[FILE]stored.pdf|report.pdf",
            "streaming": False,
        }
    )
    await back_queue.put({"message_id": "message-1", "type": "end", "data": ""})

    sent = []

    async def send_json(payload):
        sent.append(payload)

    async def send_error(*_args):
        raise AssertionError("send_error should not be called")

    await service.handle_chat_ws_send(
        post_data={
            "message": "question",
            "message_id": "message-1",
        },
        conf_list=[],
        chat_bridge=bridge,
        send_json=send_json,
        send_error=send_error,
    )

    assert len(saved) == 1
    _, parts, agent_stats, refs = saved[0]
    assert parts == [
        {"type": "plain", "text": "answer"},
        {"type": "file", "attachment_id": "attachment-1"},
        {"type": "tool_call", "tool_calls": [{"id": "tool-1", "name": "search"}]},
    ]
    assert agent_stats == {"latency": 3}
    assert refs == {"used": [{"url": "https://example.com", "title": "Tool source"}]}
    assert "_api_key_allow_admin_role" not in chat_queue.put.await_args.args[0][2]
    assert not any(item.get("data") == "ignored" for item in sent)
    assert any(item.get("type") == "refs" for item in sent)


@pytest.mark.asyncio
async def test_prepare_chat_send_treats_username_as_caller_declared_data():
    service = _service()
    service.astrbot_config_mgr = SimpleNamespace(
        get_conf_list=lambda: [],
        confs={
            "default": {},
            "active-profile": {},
        },
    )
    service.ensure_chat_session = AsyncMock(return_value=None)

    username, session_id, config_id = await service.prepare_chat_send(
        {"username": "42", "session_id": "profile-admin-session"},
        [],
    )
    assert (username, session_id, config_id) == ("42", "profile-admin-session", None)


@pytest.mark.asyncio
async def test_handle_chat_ws_send_hides_internal_bridge_errors(monkeypatch):
    service = _service()
    back_queue = asyncio.Queue()
    chat_queue = asyncio.Queue()
    service.prepare_chat_send = AsyncMock(return_value=("alice", "session-1", None))
    service.update_session_config_route = AsyncMock(return_value=None)
    logger = MagicMock()
    monkeypatch.setattr(open_api_service_module, "logger", logger)
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "get_or_create_back_queue",
        lambda *_args: back_queue,
    )
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "get_or_create_queue",
        lambda *_args: chat_queue,
    )
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "remove_back_queue",
        MagicMock(),
    )

    async def build_user_message_parts(_message):
        return [{"type": "plain", "text": "question"}]

    async def insert_user_message(*_args):
        raise RuntimeError(_SENSITIVE_INTERNAL_ERROR)

    bridge = OpenApiWebSocketChatBridge(
        build_user_message_parts=build_user_message_parts,
        create_attachment_from_file=AsyncMock(),
        extract_web_search_refs=lambda *_args: {},
        insert_user_message=insert_user_message,
        save_bot_message=AsyncMock(),
    )
    errors: list[tuple[str, str]] = []

    async def send_json(_payload):
        return None

    async def send_error(message: str, code: str) -> None:
        errors.append((message, code))

    await service.handle_chat_ws_send(
        post_data={"message": "question", "message_id": "message-1"},
        conf_list=[],
        chat_bridge=bridge,
        send_json=send_json,
        send_error=send_error,
    )

    assert errors == [("Failed to process message", "PROCESSING_ERROR")]
    rendered_logs = " ".join(
        str(call)
        for call in (*logger.error.call_args_list, *logger.exception.call_args_list)
    )
    _assert_no_sensitive_fragments(rendered_logs)


@pytest.mark.asyncio
async def test_open_api_session_and_route_errors_hide_internal_details(monkeypatch):
    service = _service()
    logger = MagicMock()
    monkeypatch.setattr(open_api_service_module, "logger", logger)

    service.db.get_platform_session_by_id = AsyncMock(return_value=None)
    service.db.create_platform_session = AsyncMock(
        side_effect=RuntimeError(_SENSITIVE_INTERNAL_ERROR)
    )
    session_error = await service.ensure_chat_session("alice", "session-1")

    service.umop_config_router = SimpleNamespace(
        update_route=AsyncMock(side_effect=RuntimeError(_SENSITIVE_INTERNAL_ERROR))
    )
    route_error = await service.update_session_config_route(
        username="alice",
        session_id="session-1",
        config_id="custom",
    )

    assert session_error == "Failed to create session"
    assert route_error == "Failed to update chat config route"
    rendered_logs = " ".join(str(call) for call in logger.error.call_args_list)
    _assert_no_sensitive_fragments(rendered_logs)


@pytest.mark.asyncio
async def test_open_api_session_rejects_same_owner_non_webchat_session():
    service = _service()
    service.db.create_platform_session = AsyncMock()
    service.db.get_platform_session_by_id = AsyncMock(
        return_value=SimpleNamespace(creator="alice", platform_id="telegram")
    )

    assert await service.ensure_chat_session("alice", "telegram-session") == (
        "session_id belongs to another username"
    )
    service.db.create_platform_session.assert_not_called()


@pytest.mark.asyncio
async def test_open_api_send_message_delegates_to_platform_manager():
    service = _service()
    calls: list[tuple[object, object]] = []

    async def _send_to_session(session, message_chain):
        calls.append((session, message_chain))
        return PlatformSendResult(
            platform_id="webchat-main",
            success=True,
            target="test-session",
            message_count=1,
        )

    service.platform_manager.send_to_session = _send_to_session

    await service.send_message(
        {
            "umo": "webchat-main:FriendMessage:test-session",
            "message": "hello",
        }
    )

    assert len(calls) == 1
    session, message_chain = calls[0]
    assert str(session) == "webchat-main:FriendMessage:test-session"
    assert message_chain.chain[0].text == "hello"


@pytest.mark.asyncio
async def test_open_api_send_message_hides_malformed_umo_parser_details(
    monkeypatch, caplog
):
    service = _service()

    def fail_parse(_umo: str):
        raise RuntimeError(_SENSITIVE_INTERNAL_ERROR)

    monkeypatch.setattr(
        open_api_service_module.MessageSession,
        "from_str",
        fail_parse,
    )

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        with pytest.raises(OpenApiServiceError) as exc_info:
            await service.send_message({"umo": "malformed", "message": "hello"})

    assert str(exc_info.value) == "Invalid umo"
    assert exc_info.value.status_code == 400
    assert caplog.records
    _assert_no_sensitive_fragments(caplog.text)


@pytest.mark.asyncio
async def test_open_api_send_message_raises_when_platform_missing():
    service = _service()

    async def _send_to_session(session, message_chain):
        return PlatformSendResult(
            platform_id=session.platform_id,
            success=False,
            target=session.session_id,
            message_count=len(message_chain.chain),
            error_message="platform adapter not found",
        )

    service.platform_manager.send_to_session = _send_to_session

    with pytest.raises(
        OpenApiServiceError,
        match="Bot not found or not running for platform: platform-not-running",
    ):
        await service.send_message(
            {
                "umo": "platform-not-running:FriendMessage:test-session",
                "message": "hello",
            }
        )


@pytest.mark.asyncio
async def test_open_api_send_message_redacts_adapter_error(monkeypatch):
    service = _service()
    logger = MagicMock()
    monkeypatch.setattr(open_api_service_module, "logger", logger)
    sensitive_error = (
        "api_key=adapter-secret Bearer adapter-token password=adapter-password "
        "https://internal.example.test/adapter "
        r"C:\\AstrBot\\data\\adapter.json /srv/astrbot/data/adapter.json"
    )

    async def _send_to_session(session, message_chain):
        return PlatformSendResult(
            platform_id=session.platform_id,
            success=False,
            target=session.session_id,
            message_count=len(message_chain.chain),
            error_message=sensitive_error,
        )

    service.platform_manager.send_to_session = _send_to_session

    with pytest.raises(OpenApiServiceError) as exc_info:
        await service.send_message(
            {
                "umo": "telegram:FriendMessage:test-session",
                "message": "hello",
            }
        )

    assert str(exc_info.value) == "Internal server error"
    assert exc_info.value.status_code == 500
    rendered_log = " ".join(str(arg) for arg in logger.error.call_args.args)
    for sensitive_fragment in (
        "adapter-secret",
        "adapter-token",
        "adapter-password",
        "internal.example.test",
        r"C:\\AstrBot\\data\\adapter.json",
        "/srv/astrbot/data/adapter.json",
    ):
        assert sensitive_fragment not in rendered_log
    assert "exc_info" not in logger.error.call_args.kwargs


@pytest.mark.asyncio
async def test_ws_handshake_and_send_use_explicit_capabilities(tmp_path):
    from astrbot.core.auth.models import AuthContext, Resource, Subject
    from astrbot.core.auth.service import AuthorizationService
    from astrbot.core.db.sqlite import SQLiteDatabase
    from astrbot.dashboard.services.open_api_service import OpenApiService

    db = SQLiteDatabase(str(tmp_path / "ws-auth.db"))
    await db.initialize()
    authorization = AuthorizationService(db)
    await authorization.start()
    created = await db.create_api_key(
        name="chat-ws",
        key_hash="hash-ws",
        key_prefix="abk_ws",
        scopes=["chat"],
        created_by="test",
    )
    service = _service()
    service.authorization = authorization
    subject = Subject.api_key(created.key_id)
    context = AuthContext(subject=subject, source="api_key", authenticated=True)
    handshake = await authorization.authorize(
        subject,
        "session.read",
        Resource.named("webchat", "socket"),
        context,
    )
    assert handshake.allowed

    service.prepare_chat_send = AsyncMock(return_value=("alice", "session-1", None))
    errors: list[tuple[str, str]] = []

    async def send_json(_payload):
        return None

    async def send_error(message: str, code: str) -> None:
        errors.append((message, code))

    await service.handle_chat_ws_send(
        post_data={"message": "hello", "username": "alice"},
        conf_list=[],
        chat_bridge=_bridge(),
        send_json=send_json,
        send_error=send_error,
        api_key_principal={"key_id": created.key_id, "scopes": ["chat"]},
    )
    assert errors == [("Authorization denied", "FORBIDDEN")]

    await authorization.grant_capability(
        subject=subject,
        action="session.manage",
        resource=OpenApiService.chat_user_resource("alice"),
    )
    errors.clear()
    await service.handle_chat_ws_send(
        post_data={"message": "hello", "username": "alice"},
        conf_list=[],
        chat_bridge=_bridge(),
        send_json=send_json,
        send_error=send_error,
        api_key_principal={"key_id": created.key_id, "scopes": ["chat"]},
    )
    assert errors == [
        (
            "Message content is empty (reply only is not allowed)",
            "INVALID_MESSAGE",
        )
    ]
    await authorization.close()
    await db.close()
