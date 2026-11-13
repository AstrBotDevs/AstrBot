from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest

from astrbot.api.platform import Group
from astrbot.core.message.mention_projection import project_self_mentions
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
    AiocqhttpAdapter,
)


@pytest.mark.asyncio
async def test_aiocqhttp_get_group_enriches_inbound_group():
    event = AiocqhttpMessageEvent.__new__(AiocqhttpMessageEvent)
    event.message_obj = SimpleNamespace(
        group=Group(group_id="123", group_name="Inbound name"),
        group_id="123",
        self_id="bot-1",
    )
    event.bot = SimpleNamespace(
        call_action=AsyncMock(
            side_effect=[
                {"group_name": "Fetched name", "member_count": 2},
                [
                    {"user_id": 1, "role": "owner", "nickname": "Owner"},
                    {"user_id": 2, "role": "admin", "nickname": "Admin"},
                ],
            ],
        )
    )

    group = await event.get_group()

    assert group.group_name == "Fetched name"
    assert group.group_owner == "1"
    assert group.group_admins == ["2"]
    assert group.member_count == 2
    assert [member.user_id for member in group.members] == ["1", "2"]


@pytest.mark.asyncio
async def test_aiocqhttp_get_group_keeps_partial_info_when_members_fail():
    event = AiocqhttpMessageEvent.__new__(AiocqhttpMessageEvent)
    event.message_obj = SimpleNamespace(
        group=Group(group_id="123", group_name="Inbound name"),
        group_id="123",
        self_id="bot-1",
    )
    event.bot = SimpleNamespace(
        call_action=AsyncMock(
            side_effect=[
                {"group_name": "Fetched name", "member_count": 8},
                RuntimeError("member API unavailable"),
            ],
        )
    )

    group = await event.get_group()

    assert group.group_name == "Fetched name"
    assert group.member_count == 8
    assert group.members is None


@pytest.mark.asyncio
async def test_aiocqhttp_get_group_keeps_inbound_info_when_group_info_fails():
    event = AiocqhttpMessageEvent.__new__(AiocqhttpMessageEvent)
    event.message_obj = SimpleNamespace(
        group=Group(group_id="123", group_name="Inbound name"),
        group_id="123",
        self_id="bot-1",
    )
    event.bot = SimpleNamespace(
        call_action=AsyncMock(
            side_effect=[
                RuntimeError("group API unavailable"),
                [],
            ],
        )
    )

    group = await event.get_group()

    assert group is event.message_obj.group
    assert group.group_name == "Inbound name"
    assert group.member_count == 0
    assert group.members == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("group_id", "expected_api_group_id"),
    [
        (456, 456),
        ("room-alpha", "room-alpha"),
    ],
)
async def test_aiocqhttp_get_group_honors_explicit_group_id(
    group_id,
    expected_api_group_id,
):
    event = AiocqhttpMessageEvent.__new__(AiocqhttpMessageEvent)
    event.message_obj = SimpleNamespace(
        group=Group(group_id="123", group_name="Current group"),
        group_id="123",
        self_id="bot-1",
    )
    event.bot = SimpleNamespace(
        call_action=AsyncMock(
            side_effect=[
                {"group_name": "Explicit group", "member_count": 0},
                [],
            ],
        )
    )

    group = await event.get_group(group_id=group_id)

    assert group.group_id == str(group_id)
    assert group.group_name == "Explicit group"
    assert group is not event.message_obj.group
    assert event.bot.call_action.await_args_list == [
        call(
            "get_group_info",
            group_id=expected_api_group_id,
            self_id="bot-1",
        ),
        call(
            "get_group_member_list",
            group_id=expected_api_group_id,
            self_id="bot-1",
        ),
    ]


@pytest.mark.asyncio
async def test_aiocqhttp_repeated_self_mentions_keep_positions_and_later_text():
    from aiocqhttp import Event

    adapter = AiocqhttpAdapter.__new__(AiocqhttpAdapter)
    adapter.bot = SimpleNamespace(call_action=AsyncMock(return_value={"card": "清漪"}))
    event = Event.from_payload(
        {
            "post_type": "message",
            "message_type": "group",
            "self_id": 123,
            "user_id": 456,
            "group_id": 789,
            "sender": {"user_id": 456, "nickname": "Tester"},
            "message_id": 1,
            "message": [
                {"type": "at", "data": {"qq": 123}},
                {"type": "text", "data": {"text": " 先总结，"}},
                {"type": "at", "data": {"qq": 123}},
                {"type": "text", "data": {"text": " 再检查"}},
                {"type": "at", "data": {"qq": 123}},
                {"type": "at", "data": {"qq": 123}},
            ],
        }
    )

    abm = await adapter._convert_handle_message_event(event)
    raw_text = abm.message_str
    final_text = raw_text.strip() + "继续检查"
    trim = len(raw_text) - len(raw_text.lstrip())

    assert (
        project_self_mentions(final_text, abm._self_mention_spans, trim)
        == "@清漪（you） 先总结，@清漪（you） 再检查@清漪（you） @清漪（you） 继续检查"
    )
