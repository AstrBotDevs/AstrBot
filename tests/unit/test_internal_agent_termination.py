"""Ensure terminated sessions cannot enter a new internal LLM request."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.core.pipeline.process_stage.method.agent_sub_stages import internal
from astrbot.core.platform.message_type import MessageType


def build_event(is_stopped: Mock):
    """Build the minimum event shape needed before agent construction."""
    return SimpleNamespace(
        unified_msg_origin="Perrin:FriendMessage:1",
        message_str="hello",
        message_obj=SimpleNamespace(message=[]),
        get_extra=Mock(return_value=None),
        get_message_type=Mock(return_value=MessageType.GROUP_MESSAGE),
        get_platform_name=Mock(return_value="aiocqhttp"),
        is_stopped=is_stopped,
        send_typing=AsyncMock(),
        stop_typing=AsyncMock(),
    )


async def drain(stage, event):
    """Exhaust the stage's async generator."""
    async for _ in stage.process(event, ""):
        pass


@pytest.mark.asyncio
async def test_stopped_event_exits_before_typing_or_lock(monkeypatch):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_reasoning = False
    event = build_event(Mock(return_value=True))
    acquire = Mock()
    monkeypatch.setattr(internal, "try_capture_follow_up", Mock(return_value=None))
    monkeypatch.setattr(internal.session_lock_manager, "acquire_lock", acquire)

    await drain(stage, event)

    event.send_typing.assert_not_awaited()
    acquire.assert_not_called()


@pytest.mark.asyncio
async def test_termination_while_waiting_for_lock_exits_before_agent(monkeypatch):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_reasoning = False
    event = build_event(Mock(side_effect=[False, True]))
    monkeypatch.setattr(internal, "try_capture_follow_up", Mock(return_value=None))
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))

    class TerminatingLock:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(
        internal.session_lock_manager,
        "acquire_lock",
        Mock(return_value=TerminatingLock()),
    )

    await drain(stage, event)

    event.send_typing.assert_awaited_once()
    event.stop_typing.assert_awaited_once()


@pytest.mark.asyncio
async def test_wake_prefix_rejection_does_not_register_pending_text(monkeypatch):
    """Reject unmatched requests before mutating the merge queue.

    Args:
        monkeypatch: Scoped replacement fixture for hooks and lock boundaries.
    """
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_reasoning = False
    event = build_event(Mock(return_value=False))
    event.get_message_type.return_value = MessageType.FRIEND_MESSAGE
    event.get_message_str = Mock(return_value="hello")
    monkeypatch.setattr(internal, "try_capture_follow_up", Mock(return_value=None))
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    prepare = AsyncMock()
    register = Mock()
    acquire = Mock()
    monkeypatch.setattr(internal, "_prepare_file_attachments", prepare)
    monkeypatch.setattr(internal._inbound_reply_merger, "register", register)
    monkeypatch.setattr(internal.session_lock_manager, "acquire_lock", acquire)

    async for _ in stage.process(event, "/ask"):
        pass

    prepare.assert_not_awaited()
    register.assert_not_called()
    acquire.assert_not_called()
    event.send_typing.assert_not_awaited()


@pytest.mark.asyncio
async def test_attachments_are_prepared_before_waiting_for_session_lock(monkeypatch):
    """Keep upstream file preparation outside the session lock.

    Args:
        monkeypatch: Scoped replacement fixture for attachment and lock handling.
    """
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_reasoning = False
    event = build_event(Mock(side_effect=[False, True]))
    monkeypatch.setattr(internal, "try_capture_follow_up", Mock(return_value=None))
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    prepare = AsyncMock()
    lock = AsyncMock()
    acquire = Mock(return_value=lock)
    order = Mock()
    order.attach_mock(prepare, "prepare")
    order.attach_mock(acquire, "acquire")
    monkeypatch.setattr(internal, "_prepare_file_attachments", prepare)
    monkeypatch.setattr(internal.session_lock_manager, "acquire_lock", acquire)

    await drain(stage, event)

    prepare.assert_awaited_once_with(event)
    acquire.assert_called_once_with(event.unified_msg_origin)
    assert [item[0] for item in order.mock_calls[:2]] == ["prepare", "acquire"]
