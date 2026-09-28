from types import SimpleNamespace

import pytest

from astrbot.dashboard.services.open_api_service import (
    OpenApiService,
    OpenApiServiceError,
    OpenApiWebSocketChatBridge,
)


def _service() -> OpenApiService:
    core_lifecycle = SimpleNamespace(
        platform_manager=SimpleNamespace(platform_insts=[]),
        platform_message_history_manager=None,
        astrbot_config_mgr=SimpleNamespace(
            confs={"default": {"admins_id": ["admin-user"]}}
        ),
    )
    return OpenApiService(SimpleNamespace(), core_lifecycle)


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
        return ["chat", "chat:admin"], None

    async def handle_chat_ws_send(**kwargs):
        handled.append(
            {
                "post_data": kwargs["post_data"],
                "allow_admin_username": kwargs["allow_admin_username"],
            }
        )

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
    assert handled == [
        {
            "post_data": {"t": "send", "message": "hello"},
            "allow_admin_username": True,
        }
    ]


@pytest.mark.asyncio
async def test_prepare_chat_send_rejects_configured_admin_username():
    """The shared HTTP/WS boundary must reject administrator impersonation."""
    service = _service()

    with pytest.raises(
        OpenApiServiceError,
        match="username is reserved for an AstrBot administrator",
    ):
        await service.prepare_chat_send(
            {"username": "admin-user", "message": "hello"},
            [],
        )


@pytest.mark.asyncio
async def test_prepare_chat_send_allows_admin_username_with_subscope(monkeypatch):
    """The explicit chat-admin subscope should preserve legitimate admin calls."""
    service = _service()

    async def ensure_chat_session(_username, _session_id):
        return None

    monkeypatch.setattr(service, "ensure_chat_session", ensure_chat_session)

    username, session_id, config_id = await service.prepare_chat_send(
        {
            "username": "admin-user",
            "session_id": "admin-session",
            "message": "hello",
        },
        [],
        allow_admin_username=True,
    )

    assert username == "admin-user"
    assert session_id == "admin-session"
    assert config_id is None
