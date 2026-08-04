"""Tests for Main.handle_session_control_agent result routing.

Covers the two branches introduced by the session-waiter return-value change:
- handler returns a MessageEventResult -> yield it, then stop_event
- handler returns None -> no yield, just stop_event
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata


class _ConcreteEvent(AstrMessageEvent):
    async def send(self, message):
        await super().send(message)


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


def _build_main():
    """Construct a Main instance without running its heavy __init__."""
    from astrbot.builtin_stars.astrbot.main import Main

    main = Main.__new__(Main)
    return main


async def _collect(gen):
    """Drain an async generator into a list of yielded values."""
    out = []
    async for item in gen:
        out.append(item)
    return out


@pytest.mark.asyncio
async def test_yields_message_event_result_when_trigger_returns_one():
    """When trigger returns a MessageEventResult, the handler should yield it."""
    main = _build_main()
    event = _make_event()
    expected = MessageEventResult().message("先见之明")

    fake_filter = MagicMock()
    fake_filter.filter = MagicMock(return_value="sid")
    with (
        patch(
            "astrbot.builtin_stars.astrbot.main.FILTERS",
            [fake_filter],
        ),
        patch(
            "astrbot.builtin_stars.astrbot.main.USER_SESSIONS",
            {"sid": MagicMock()},
        ),
        patch(
            "astrbot.builtin_stars.astrbot.main.SessionWaiter.trigger",
            new=AsyncMock(return_value=expected),
        ),
    ):
        yielded = await _collect(main.handle_session_control_agent(event))

    assert yielded == [expected]
    assert event.is_stopped() is True


@pytest.mark.asyncio
async def test_no_yield_when_trigger_returns_none():
    """When trigger returns None, the handler should not yield and should stop."""
    main = _build_main()
    event = _make_event()

    fake_filter = MagicMock()
    fake_filter.filter = MagicMock(return_value="sid")
    with (
        patch(
            "astrbot.builtin_stars.astrbot.main.FILTERS",
            [fake_filter],
        ),
        patch(
            "astrbot.builtin_stars.astrbot.main.USER_SESSIONS",
            {"sid": MagicMock()},
        ),
        patch(
            "astrbot.builtin_stars.astrbot.main.SessionWaiter.trigger",
            new=AsyncMock(return_value=None),
        ),
    ):
        yielded = await _collect(main.handle_session_control_agent(event))

    assert yielded == []
    assert event.is_stopped() is True


@pytest.mark.asyncio
async def test_no_op_when_no_session_matches():
    """When no session_filter matches, nothing happens and event is not stopped."""
    main = _build_main()
    event = _make_event()

    with (
        patch("astrbot.builtin_stars.astrbot.main.FILTERS", []),
        patch("astrbot.builtin_stars.astrbot.main.USER_SESSIONS", {}),
    ):
        yielded = await _collect(main.handle_session_control_agent(event))

    assert yielded == []
    assert event.is_stopped() is False
