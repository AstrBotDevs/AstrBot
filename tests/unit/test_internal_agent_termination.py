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
