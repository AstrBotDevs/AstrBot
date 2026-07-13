import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.dashboard.services import chat_service
from astrbot.dashboard.services.chat_service import ChatService
from astrbot.dashboard.services.chat_service import poll_webchat_stream_result


class _QueueThatRaises:
    def __init__(self, exc: BaseException):
        self._exc = exc

    async def get(self):
        raise self._exc


class _QueueWithResult:
    def __init__(self, result):
        self._result = result

    async def get(self):
        return self._result


@pytest.mark.asyncio
async def test_poll_webchat_stream_result_breaks_on_cancelled_error():
    result, should_break = await poll_webchat_stream_result(
        _QueueThatRaises(asyncio.CancelledError()),
        "alice",
    )

    assert result is None
    assert should_break is True


@pytest.mark.asyncio
async def test_poll_webchat_stream_result_continues_on_generic_exception():
    result, should_break = await poll_webchat_stream_result(
        _QueueThatRaises(RuntimeError("boom")),
        "alice",
    )

    assert result is None
    assert should_break is False


@pytest.mark.asyncio
async def test_poll_webchat_stream_result_returns_queue_payload():
    payload = {"type": "end", "data": ""}

    result, should_break = await poll_webchat_stream_result(
        _QueueWithResult(payload),
        "alice",
    )

    assert result == payload
    assert should_break is False


@pytest.mark.asyncio
async def test_chat_stream_disconnect_requests_agent_stop(monkeypatch):
    service = object.__new__(ChatService)
    service.running_convs = {}
    service.build_user_message_parts = AsyncMock(
        return_value=[{"type": "plain", "text": "hello"}]
    )
    service.save_bot_message = AsyncMock()

    stop_agent = Mock(return_value=1)
    monkeypatch.setattr(
        chat_service.active_event_registry,
        "request_agent_stop_all",
        stop_agent,
    )
    monkeypatch.setattr(
        chat_service,
        "poll_webchat_stream_result",
        AsyncMock(return_value=(None, True)),
    )

    session_id = "disconnect-session"
    stream = await service.build_chat_stream(
        "alice",
        {
            "message": "hello",
            "session_id": session_id,
            "_skip_user_history": True,
        },
    )

    try:
        await anext(stream)
        with pytest.raises(StopAsyncIteration):
            await anext(stream)
    finally:
        await stream.aclose()
        chat_service.webchat_queue_mgr.remove_queues(session_id)

    stop_agent.assert_called_once_with(
        chat_service.build_thread_unified_msg_origin("alice", session_id)
    )


@pytest.mark.asyncio
async def test_chat_stream_close_requests_agent_stop(monkeypatch):
    service = object.__new__(ChatService)
    service.running_convs = {}
    service.build_user_message_parts = AsyncMock(
        return_value=[{"type": "plain", "text": "hello"}]
    )
    service.save_bot_message = AsyncMock()

    stop_agent = Mock(return_value=1)
    monkeypatch.setattr(
        chat_service.active_event_registry,
        "request_agent_stop_all",
        stop_agent,
    )

    session_id = "closed-session"
    stream = await service.build_chat_stream(
        "alice",
        {
            "message": "hello",
            "session_id": session_id,
            "_skip_user_history": True,
        },
    )

    try:
        await anext(stream)
        await stream.aclose()
    finally:
        chat_service.webchat_queue_mgr.remove_queues(session_id)

    stop_agent.assert_called_once_with(
        chat_service.build_thread_unified_msg_origin("alice", session_id)
    )
