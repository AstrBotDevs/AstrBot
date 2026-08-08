"""Tests for session_waiter.trigger return value propagation."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.utils.session_waiter import (
    FILTERS,
    USER_SESSIONS,
    SessionController,
    SessionFilter,
    SessionWaiter,
    session_waiter,
)

SESSION_ID = "fixed_session_id"


class _ConcreteEvent(AstrMessageEvent):
    async def send(self, message):
        await super().send(message)


class _IdFilter(SessionFilter):
    def filter(self, event: AstrMessageEvent) -> str:
        return SESSION_ID


def _make_event() -> _ConcreteEvent:
    meta = PlatformMetadata(name="test", description="t", id="test_id")
    msg = AstrBotMessage()
    msg.type = MessageType.FRIEND_MESSAGE
    msg.self_id = "bot"
    msg.session_id = "s"
    msg.message_id = "m"
    msg.sender = MessageMember(user_id="u", nickname="U")
    msg.message_str = "hi"
    return _ConcreteEvent("hi", msg, meta, "s")


@pytest.fixture
def waiter_handler():
    """Return a mutable holder so each test can install its own handler.

    Also cleans up the module-global USER_SESSIONS / FILTERS so tests stay
    isolated even if the waiter task is interrupted.
    """

    holder = {}

    @session_waiter(timeout=5, record_history_chains=False)
    async def waiter(controller: SessionController, event: AstrMessageEvent):
        handler = holder["handler"]
        if handler is None:
            return None
        return await handler(controller, event)

    holder["waiter"] = waiter
    holder["handler"] = None
    yield holder
    # Teardown: stop any still-pending session and clear globals.
    for session in list(USER_SESSIONS.values()):
        session.session_controller.stop()
    USER_SESSIONS.clear()
    FILTERS.clear()


async def _start_waiter(holder) -> asyncio.Task:
    """Register the waiter (which blocks on the controller future) in background."""
    event = _make_event()
    task = asyncio.create_task(holder["waiter"](event, session_filter=_IdFilter()))
    # Yield control so the waiter registers itself in USER_SESSIONS.
    await asyncio.sleep(0)
    return task


@pytest.mark.asyncio
async def test_trigger_returns_message_event_result(waiter_handler):
    """trigger should propagate the handler's returned MessageEventResult."""
    expected = MessageEventResult().message("先见之明")
    waiter_handler["handler"] = AsyncMock(return_value=expected)

    task = await _start_waiter(waiter_handler)
    result = await SessionWaiter.trigger(SESSION_ID, _make_event())

    assert result is expected
    # register_wait is still pending; stop it cleanly.
    for session in list(USER_SESSIONS.values()):
        session.session_controller.stop()
    await task


@pytest.mark.asyncio
async def test_trigger_returns_none_when_handler_returns_none(waiter_handler):
    """trigger should return None when the handler returns None."""
    waiter_handler["handler"] = AsyncMock(return_value=None)

    task = await _start_waiter(waiter_handler)
    result = await SessionWaiter.trigger(SESSION_ID, _make_event())

    assert result is None
    for session in list(USER_SESSIONS.values()):
        session.session_controller.stop()
    await task


@pytest.mark.asyncio
async def test_trigger_returns_none_when_no_session():
    """trigger should return None when there is no registered session."""
    event = _make_event()
    result = await SessionWaiter.trigger("nonexistent_session", event)
    assert result is None


@pytest.mark.asyncio
async def test_trigger_returns_none_when_handler_raises(waiter_handler):
    """trigger should return None (and stop the controller) when the handler raises.

    The still-pending register_wait task will re-raise the exception after we
    stop the controller, so we swallow it explicitly.
    """
    waiter_handler["handler"] = AsyncMock(side_effect=RuntimeError("boom"))

    task = await _start_waiter(waiter_handler)
    result = await SessionWaiter.trigger(SESSION_ID, _make_event())

    assert result is None
    # The controller was stopped with the exception; register_wait re-raises it.
    with pytest.raises(RuntimeError, match="boom"):
        await task
