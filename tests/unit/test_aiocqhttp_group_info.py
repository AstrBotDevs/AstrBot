from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest

from astrbot.core.platform import Group
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

pytestmark = pytest.mark.platform


@pytest.mark.asyncio
async def test_aiocqhttp_get_group_enriches_inbound_group():
    event = AiocqhttpMessageEvent.__new__(AiocqhttpMessageEvent)
    event.message_obj = SimpleNamespace(
        group=Group(group_id="123", group_name="Inbound name"),
        group_id="123",
        self_id="bot-1",
    )
    event._bot = SimpleNamespace(
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

    assert group is not event.message_obj.group
    assert event.message_obj.group.group_name == "Inbound name"
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
    event._bot = SimpleNamespace(
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
    event._bot = SimpleNamespace(
        call_action=AsyncMock(
            side_effect=[
                RuntimeError("group API unavailable"),
                [],
            ],
        )
    )

    group = await event.get_group()

    assert group is not event.message_obj.group
    assert event.message_obj.group.group_name == "Inbound name"
    assert event.message_obj.group.members is None
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
    event._bot = SimpleNamespace(
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
    assert event._bot.call_action.await_args_list == [
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
async def test_aiocqhttp_get_group_skips_member_list_when_count_is_over_cap():
    event = AiocqhttpMessageEvent.__new__(AiocqhttpMessageEvent)
    event.message_obj = SimpleNamespace(
        group=Group(group_id="123", group_name="Inbound name", group_owner="9"),
        group_id="123",
        self_id="bot-1",
    )
    event._bot = SimpleNamespace(
        call_action=AsyncMock(
            return_value={"group_name": "Fetched name", "member_count": 2500},
        )
    )

    group = await event.get_group()

    assert event._bot.call_action.await_args_list == [
        call("get_group_info", group_id=123, self_id="bot-1"),
    ]
    assert group.group_name == "Fetched name"
    assert group.member_count == 2500
    assert group.members is None
    assert group.group_owner == "9"


@pytest.mark.asyncio
async def test_aiocqhttp_get_group_omits_members_when_list_is_over_cap():
    members = [
        {"user_id": index, "role": "member", "nickname": str(index)}
        for index in range(2001)
    ]
    members[0]["role"] = "owner"
    members[1]["role"] = "admin"
    event = AiocqhttpMessageEvent.__new__(AiocqhttpMessageEvent)
    event.message_obj = SimpleNamespace(
        group=Group(group_id="123", group_name="Inbound name"),
        group_id="123",
        self_id="bot-1",
    )
    event._bot = SimpleNamespace(
        call_action=AsyncMock(
            side_effect=[
                {"group_name": "Fetched name"},
                members,
            ],
        )
    )

    group = await event.get_group()

    assert event._bot.call_action.await_args_list == [
        call("get_group_info", group_id=123, self_id="bot-1"),
        call("get_group_member_list", group_id=123, self_id="bot-1"),
    ]
    assert group.members is None
    assert group.member_count == 2001
    assert group.group_owner == "0"
    assert group.group_admins == ["1"]


@pytest.mark.asyncio
async def test_aiocqhttp_get_group_still_publishes_members_at_hard_cap():
    event = AiocqhttpMessageEvent.__new__(AiocqhttpMessageEvent)
    event.message_obj = SimpleNamespace(
        group=Group(group_id="123", group_name="Inbound name"),
        group_id="123",
        self_id="bot-1",
    )
    event._bot = SimpleNamespace(
        call_action=AsyncMock(
            side_effect=[
                {"group_name": "Fetched name"},
                [{"user_id": index, "nickname": str(index)} for index in range(2000)],
            ],
        )
    )

    group = await event.get_group()

    assert group.members is not None
    assert len(group.members) == 2000
    assert group.member_count == 2000
