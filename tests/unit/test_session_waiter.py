"""Tests for the session waiter's default session identity.

Regression coverage for the group-chat interception bug: a waiter registered by
one group member must not be triggered by a different member of the same group,
while the same member must still be isolated across different sessions.
"""

from __future__ import annotations

import asyncio

import pytest

from astrbot.core.message.components import Plain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.utils.session_waiter import (
    USER_SESSIONS,
    DefaultSessionFilter,
    SessionController,
    SessionWaiter,
    session_waiter,
)

PLATFORM_META = PlatformMetadata(
    name="aiocqhttp",
    description="test platform",
    id="aiocqhttp",
)


def make_event(
    sender_id: str,
    session_id: str,
    message_type: MessageType = MessageType.GROUP_MESSAGE,
    text: str = "hello",
) -> AstrMessageEvent:
    """Build a minimal group/private message event.

    Args:
        sender_id: ID of the member that sent the message.
        session_id: Platform session ID (group ID for group messages).
        message_type: Message type of the event.
        text: Plain text payload of the message.

    Returns:
        A usable ``AstrMessageEvent`` for session-identity assertions.
    """
    message_obj = AstrBotMessage()
    message_obj.type = message_type
    message_obj.self_id = "bot"
    message_obj.session_id = session_id
    message_obj.message_id = "1"
    message_obj.sender = MessageMember(user_id=sender_id, nickname=sender_id)
    message_obj.message = [Plain(text=text)]
    message_obj.message_str = text
    message_obj.raw_message = None
    if message_type == MessageType.GROUP_MESSAGE:
        message_obj.group_id = session_id
    return AstrMessageEvent(
        message_str=text,
        message_obj=message_obj,
        platform_meta=PLATFORM_META,
        session_id=session_id,
    )


def test_default_filter_separates_members_of_the_same_group():
    """Two members of one group must map to different session identities."""
    session_filter = DefaultSessionFilter()
    event_a = make_event("member_a", "group_1")
    event_b = make_event("member_b", "group_1")

    assert session_filter.filter(event_a) != session_filter.filter(event_b)


def test_default_filter_is_stable_for_the_same_member():
    """The same member in the same group must map to one session identity."""
    session_filter = DefaultSessionFilter()
    first = make_event("member_a", "group_1", text="one")
    second = make_event("member_a", "group_1", text="two")

    assert session_filter.filter(first) == session_filter.filter(second)


def test_default_filter_separates_sessions_of_the_same_member():
    """One member must not share a waiter across groups or private chats."""
    session_filter = DefaultSessionFilter()
    in_group_1 = make_event("member_a", "group_1")
    in_group_2 = make_event("member_a", "group_2")
    in_private = make_event(
        "member_a",
        "member_a",
        message_type=MessageType.FRIEND_MESSAGE,
    )

    identities = {
        session_filter.filter(in_group_1),
        session_filter.filter(in_group_2),
        session_filter.filter(in_private),
    }
    assert len(identities) == 3


@pytest.mark.asyncio
async def test_waiter_ignores_other_members_and_accepts_the_owner():
    """A registered waiter only fires for the member that created it."""
    USER_SESSIONS.clear()
    session_filter = DefaultSessionFilter()
    owner_event = make_event("member_a", "group_1", text="@bot")
    other_event = make_event("member_b", "group_1", text="unrelated chatter")

    triggered: list[str] = []

    @session_waiter(timeout=5)
    async def waiter(controller: SessionController, event: AstrMessageEvent) -> None:
        triggered.append(event.get_sender_id())
        controller.stop()

    waiting = asyncio.create_task(waiter(owner_event, session_filter))
    await asyncio.sleep(0)

    # A different member of the same group must not reach the waiter.
    await SessionWaiter.trigger(session_filter.filter(other_event), other_event)
    assert triggered == []

    # The owner's own follow-up message must reach the waiter.
    follow_up = make_event("member_a", "group_1", text="the real question")
    await SessionWaiter.trigger(session_filter.filter(follow_up), follow_up)
    await asyncio.wait_for(waiting, timeout=5)

    assert triggered == ["member_a"]
    assert USER_SESSIONS == {}
