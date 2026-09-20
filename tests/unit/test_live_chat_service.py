import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.websockets import WebSocketDisconnect

from astrbot.core.platform.sources.webchat.webchat_queue_mgr import webchat_queue_mgr
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


@pytest.mark.asyncio
async def test_run_websocket_session_multiplexes_chat_requests_by_default(
    monkeypatch,
):
    service = _service()
    started = asyncio.Event()
    started_requests: list[str] = []
    messages = iter(
        [
            {
                "ct": "chat",
                "t": "send",
                "session_id": "chat-session",
                "message_id": "request-1",
            },
            {
                "ct": "chat",
                "t": "send",
                "session_id": "chat-session",
                "message_id": "request-2",
            },
        ]
    )

    monkeypatch.setattr(service, "authenticate_token", lambda _token: "alice")

    async def handle_chat_message(_session, message, _send_json) -> None:
        started_requests.append(message["message_id"])
        if len(started_requests) == 2:
            started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(service, "handle_chat_message", handle_chat_message)

    async def receive_json() -> dict:
        try:
            return next(messages)
        except StopIteration as exc:
            await asyncio.wait_for(started.wait(), timeout=1)
            raise WebSocketDisconnect(1000) from exc

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

    assert started_requests == ["request-1", "request-2"]
    assert service.sessions == {}


@pytest.mark.asyncio
async def test_handle_chat_interrupt_without_message_id_targets_all_requests():
    service = _service()
    session = service.create_session("alice")
    sent: list[dict] = []
    tasks = {
        "request-1": asyncio.create_task(asyncio.Event().wait()),
        "request-2": asyncio.create_task(asyncio.Event().wait()),
    }
    session.chat_request_tasks.update(tasks)

    async def send_json(payload: dict) -> None:
        sent.append(payload)

    try:
        await service.handle_chat_message(
            session,
            {"t": "interrupt"},
            send_json,
        )

        assert session.interrupted_chat_requests == set(tasks)
        assert sent == [
            {
                "ct": "chat",
                "t": "error",
                "data": "INTERRUPTED",
                "code": "INTERRUPTED",
            }
        ]
    finally:
        await service.cleanup_session(session)


@pytest.mark.asyncio
async def test_handle_chat_message_scopes_events_to_request_by_default():
    service = _service()
    session = service.create_session("alice")
    session_id = "multiplexed-chat-session"
    message_id = "request-1"
    sent: list[dict] = []
    service.platform_history_mgr.insert = AsyncMock(
        return_value=SimpleNamespace(id=1, created_at=datetime.now(UTC))
    )
    service.build_chat_message_parts = AsyncMock(
        return_value=[{"type": "plain", "text": "hello"}]
    )
    service.ensure_chat_subscription = AsyncMock(return_value="subscription-1")

    async def send_json(payload: dict) -> None:
        sent.append(payload)

    task = asyncio.create_task(
        service.handle_chat_message(
            session,
            {
                "t": "send",
                "session_id": session_id,
                "message_id": message_id,
                "message": [{"type": "plain", "text": "hello"}],
            },
            send_json,
        )
    )

    try:
        input_queue = webchat_queue_mgr.get_or_create_queue(session_id)
        await asyncio.wait_for(input_queue.get(), timeout=1)

        await webchat_queue_mgr.put_back_queue(
            message_id,
            {
                "type": "end",
                "data": "",
                "streaming": False,
                "message_id": message_id,
            },
        )
        await asyncio.wait_for(task, timeout=1)

        assert sent[0]["type"] == "user_message_saved"
        assert sent[0]["message_id"] == message_id
        assert sent[-1]["type"] == "end"
        assert sent[-1]["message_id"] == message_id
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await service.cleanup_session(session)
        webchat_queue_mgr.remove_queues(session_id)
