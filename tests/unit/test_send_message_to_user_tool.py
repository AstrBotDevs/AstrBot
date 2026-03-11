from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.astr_main_agent_resources import SendMessageToUserTool
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.pipeline.respond.stage import RespondStage


class _DummyEvent:
    def __init__(self) -> None:
        self.unified_msg_origin = "test_platform_id:FriendMessage:session123"
        self._has_send_oper = False
        self._extras: dict[str, object] = {}
        self._result = MessageEventResult().message("duplicate reply")
        self.send = AsyncMock()

    def set_extra(self, key: str, value: object) -> None:
        self._extras[key] = value

    def get_extra(self, key: str, default=None):
        return self._extras.get(key, default)

    def get_result(self):
        return self._result


@pytest.mark.asyncio
async def test_send_message_to_user_marks_current_session_delivery():
    event = _DummyEvent()
    send_message = AsyncMock(return_value=True)
    run_context = ContextWrapper(
        context=SimpleNamespace(
            event=event,
            context=SimpleNamespace(send_message=send_message),
        ),
    )

    tool = SendMessageToUserTool()
    result = await tool.call(
        run_context,
        messages=[{"type": "plain", "text": "hello"}],
    )

    assert "Message sent to session" in result
    send_message.assert_awaited_once()
    assert event._has_send_oper is True
    assert event.get_extra("_send_message_to_user_current_session") is True


@pytest.mark.asyncio
async def test_send_message_to_user_other_session_does_not_mark_current_session():
    event = _DummyEvent()
    send_message = AsyncMock(return_value=True)
    run_context = ContextWrapper(
        context=SimpleNamespace(
            event=event,
            context=SimpleNamespace(send_message=send_message),
        ),
    )

    tool = SendMessageToUserTool()
    await tool.call(
        run_context,
        session="test_platform_id:FriendMessage:another-session",
        messages=[{"type": "plain", "text": "hello"}],
    )

    assert event._has_send_oper is False
    assert event.get_extra("_send_message_to_user_current_session") is None


@pytest.mark.asyncio
async def test_respond_stage_skips_duplicate_after_send_message_to_user():
    stage = RespondStage()
    event = _DummyEvent()
    event.set_extra("_send_message_to_user_current_session", True)

    result = await stage.process(event)

    assert result is None
    event.send.assert_not_awaited()
