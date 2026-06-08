from types import SimpleNamespace

import pytest
from starlette.websockets import WebSocketDisconnect

from astrbot.dashboard.services.live_chat_service import LiveChatService


def _service() -> LiveChatService:
    core_lifecycle = SimpleNamespace(
        astrbot_config={"dashboard": {"jwt_secret": "test-secret"}},
        plugin_manager=SimpleNamespace(),
        platform_message_history_manager=SimpleNamespace(),
    )
    return LiveChatService(SimpleNamespace(), core_lifecycle)


@pytest.mark.asyncio
async def test_run_websocket_session_closes_when_token_is_missing():
    service = _service()
    closed: list[tuple[int, str]] = []

    async def close(code: int, reason: str) -> None:
        closed.append((code, reason))

    async def receive_json() -> dict:
        raise AssertionError("receive_json should not be called")

    async def send_json(payload: dict) -> None:
        raise AssertionError(f"send_json should not be called: {payload}")

    await service.run_websocket_session(
        token=None,
        force_ct=None,
        receive_json=receive_json,
        send_json=send_json,
        close=close,
    )

    assert closed == [(1008, "Missing authentication token")]
    assert service.sessions == {}


@pytest.mark.asyncio
async def test_run_websocket_session_routes_messages_and_cleans_session(monkeypatch):
    service = _service()
    messages = iter(
        [
            {"ct": "chat", "t": "bind", "session_id": "chat-session"},
            {"t": "start_speaking", "stamp": "s1"},
        ]
    )
    routed: list[tuple[str, str, dict]] = []

    monkeypatch.setattr(service, "authenticate_token", lambda _token: "alice")

    async def handle_chat_message(session, message, _send_json) -> None:
        routed.append(("chat", session.username, message))

    async def handle_live_message(session, message, _send_json) -> None:
        routed.append(("live", session.username, message))

    monkeypatch.setattr(service, "handle_chat_message", handle_chat_message)
    monkeypatch.setattr(service, "handle_live_message", handle_live_message)

    async def receive_json() -> dict:
        try:
            return next(messages)
        except StopIteration as exc:
            raise RuntimeError("disconnect") from exc

    async def send_json(_payload: dict) -> None:
        pass

    async def close(_code: int, _reason: str) -> None:
        raise AssertionError("close should not be called")

    await service.run_websocket_session(
        token="valid",
        force_ct=None,
        receive_json=receive_json,
        send_json=send_json,
        close=close,
    )

    assert [(kind, username) for kind, username, _ in routed] == [
        ("chat", "alice"),
        ("live", "alice"),
    ]
    assert service.sessions == {}


@pytest.mark.asyncio
async def test_run_websocket_session_handles_disconnect_without_error_log(
    monkeypatch,
):
    service = _service()
    messages = iter([{"ct": "chat", "t": "bind", "session_id": "chat-session"}])
    routed: list[dict] = []

    monkeypatch.setattr(service, "authenticate_token", lambda _token: "alice")

    async def handle_chat_message(session, message, _send_json) -> None:
        routed.append({"username": session.username, "message": message})

    monkeypatch.setattr(service, "handle_chat_message", handle_chat_message)

    async def receive_json() -> dict:
        try:
            return next(messages)
        except StopIteration as exc:
            raise WebSocketDisconnect(1006) from exc

    async def send_json(_payload: dict) -> None:
        pass

    async def close(_code: int, _reason: str) -> None:
        raise AssertionError("close should not be called")

    def fail_error_log(*_args, **_kwargs) -> None:
        raise AssertionError("disconnect should not be logged as an error")

    monkeypatch.setattr(
        "astrbot.dashboard.services.live_chat_service.logger.error",
        fail_error_log,
    )

    await service.run_websocket_session(
        token="valid",
        force_ct=None,
        receive_json=receive_json,
        send_json=send_json,
        close=close,
    )

    assert routed == [
        {
            "username": "alice",
            "message": {"ct": "chat", "t": "bind", "session_id": "chat-session"},
        }
    ]
    assert service.sessions == {}
