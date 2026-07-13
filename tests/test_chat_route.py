import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.dashboard.services import chat_service
from astrbot.dashboard.services.chat_service import (
    ChatService,
    poll_webchat_stream_result,
)


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


@pytest.fixture
def chat_service_instance(monkeypatch, tmp_path):
    """Create ChatService through its public constructor for stream tests."""
    monkeypatch.setattr(chat_service, "get_astrbot_data_path", lambda: str(tmp_path))
    core_lifecycle = SimpleNamespace(
        conversation_manager=Mock(),
        platform_message_history_manager=Mock(),
        umop_config_router=Mock(),
    )
    return ChatService(Mock(), core_lifecycle)


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
async def test_chat_stream_disconnect_requests_agent_stop(
    monkeypatch,
    chat_service_instance,
):
    service = chat_service_instance
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
async def test_chat_stream_close_requests_agent_stop(
    monkeypatch,
    chat_service_instance,
):
    service = chat_service_instance
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


@pytest.mark.asyncio
async def test_chat_stream_cancellation_does_not_cancel_pending_persistence(
    monkeypatch,
    chat_service_instance,
):
    service = chat_service_instance
    service.build_user_message_parts = AsyncMock(
        return_value=[{"type": "plain", "text": "hello"}]
    )

    save_started = asyncio.Event()
    allow_save = asyncio.Event()
    save_completed = asyncio.Event()
    save_cancelled = asyncio.Event()

    async def save_bot_message(*_args, **_kwargs):
        save_started.set()
        try:
            await allow_save.wait()
        except asyncio.CancelledError:
            save_cancelled.set()
            raise
        save_completed.set()
        return None

    service.save_bot_message = save_bot_message
    monkeypatch.setattr(
        chat_service.active_event_registry,
        "request_agent_stop_all",
        Mock(return_value=1),
    )

    session_id = "cancelled-persistence-session"
    stream = await service.build_chat_stream(
        "alice",
        {
            "message": "hello",
            "session_id": session_id,
            "_skip_user_history": True,
        },
    )
    request_id = chat_service.webchat_queue_mgr.list_back_request_ids(session_id)[0]
    monkeypatch.setattr(
        chat_service,
        "poll_webchat_stream_result",
        AsyncMock(
            side_effect=[
                (
                    {
                        "type": "plain",
                        "data": "partial response",
                        "streaming": True,
                        "message_id": request_id,
                    },
                    False,
                ),
                (None, True),
            ]
        ),
    )

    try:
        await anext(stream)
        await anext(stream)
        stream_task = asyncio.create_task(anext(stream))
        await asyncio.wait_for(save_started.wait(), timeout=1)
        stream_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await stream_task

        allow_save.set()
        await asyncio.wait_for(save_completed.wait(), timeout=1)
        assert not save_cancelled.is_set()
    finally:
        allow_save.set()
        chat_service.webchat_queue_mgr.remove_queues(session_id)
