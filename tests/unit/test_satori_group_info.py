import asyncio
from unittest.mock import AsyncMock, call

import pytest

from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.sources.satori.satori_adapter import (
    SatoriPlatformAdapter,
)

pytestmark = pytest.mark.platform


async def _make_group_event(guild: dict):
    adapter = SatoriPlatformAdapter(
        {"id": "satori-test"},
        {},
        asyncio.Queue(),
    )
    login = {
        "platform": "discord",
        "user": {"id": "bot-1", "name": "AstrBot"},
    }
    message = await adapter.convert_satori_message(
        {"id": "message-1", "content": "hello"},
        {"id": "user-1", "name": "Alice"},
        {"id": "channel-1", "name": "general"},
        guild,
        login,
    )
    assert message is not None
    return adapter, message, adapter.create_event(message)


@pytest.mark.asyncio
async def test_satori_group_message_maps_event_guild_metadata():
    _, message, _ = await _make_group_event(
        {
            "id": "guild-1",
            "name": "AstrBot Users",
            "avatar": "https://example.com/guild.png",
        },
    )

    assert message.type == MessageType.GROUP_MESSAGE
    assert message.group is not None
    assert message.group.group_id == "guild-1"
    assert message.group.group_name == "AstrBot Users"
    assert message.group.group_avatar == "https://example.com/guild.png"


@pytest.mark.asyncio
async def test_satori_get_group_enriches_metadata_and_paginates_members():
    adapter, _, event = await _make_group_event(
        {"id": "guild-1", "name": "Event Name"},
    )
    adapter.logins = [
        {
            "platform": "discord",
            "user": {"id": "bot-1"},
            "features": ["guild.get", "guild.member.list"],
        },
    ]
    adapter.send_http_request = AsyncMock(
        side_effect=[
            {
                "id": "guild-1",
                "name": "Fetched Name",
                "avatar": "https://example.com/fetched.png",
            },
            {
                "data": [
                    {
                        "nick": "Alice in Guild",
                        "user": {"id": "user-1", "name": "Alice"},
                    },
                ],
                "next": "page-2",
            },
            {
                "data": [
                    {"user": {"id": "user-2", "name": "Bob"}},
                ],
            },
        ],
    )

    group = await event.get_group()

    assert group is not None
    assert group.group_id == "guild-1"
    assert group.group_name == "Fetched Name"
    assert group.group_avatar == "https://example.com/fetched.png"
    assert group.member_count == 2
    assert [(member.user_id, member.nickname) for member in group.members or []] == [
        ("user-1", "Alice in Guild"),
        ("user-2", "Bob"),
    ]
    assert adapter.send_http_request.await_args_list == [
        call(
            "POST",
            "/guild.get",
            {"guild_id": "guild-1"},
            "discord",
            "bot-1",
        ),
        call(
            "POST",
            "/guild.member.list",
            {"guild_id": "guild-1"},
            "discord",
            "bot-1",
        ),
        call(
            "POST",
            "/guild.member.list",
            {"guild_id": "guild-1", "next": "page-2"},
            "discord",
            "bot-1",
        ),
    ]


@pytest.mark.asyncio
async def test_satori_get_group_falls_back_when_apis_are_unavailable():
    adapter, _, event = await _make_group_event(
        {
            "id": "guild-1",
            "name": "Event Name",
            "avatar": "https://example.com/event.png",
        },
    )
    adapter.send_http_request = AsyncMock(side_effect=[{}, {}])

    group = await event.get_group()

    assert group is not None
    assert group.group_id == "guild-1"
    assert group.group_name == "Event Name"
    assert group.group_avatar == "https://example.com/event.png"
    assert group.members is None
    assert group.member_count is None


@pytest.mark.asyncio
async def test_satori_get_group_falls_back_when_api_calls_raise():
    adapter, _, event = await _make_group_event(
        {"id": "guild-1", "name": "Event Name"},
    )
    adapter.send_http_request = AsyncMock(
        side_effect=RuntimeError("HTTP session unavailable")
    )

    group = await event.get_group()

    assert group is not None
    assert group.group_name == "Event Name"
    assert group.members is None
    assert group.member_count is None


@pytest.mark.asyncio
async def test_satori_get_group_respects_declared_unsupported_features():
    adapter, _, event = await _make_group_event(
        {"id": "guild-1", "name": "Event Name"},
    )
    adapter.logins = [
        {
            "platform": "discord",
            "user": {"id": "bot-1"},
            "features": [],
        },
    ]
    adapter.send_http_request = AsyncMock()

    group = await event.get_group()

    assert group is not None
    assert group.group_name == "Event Name"
    adapter.send_http_request.assert_not_awaited()


@pytest.mark.asyncio
async def test_satori_get_group_caps_member_pages_and_omits_truncated_list():
    adapter, _, event = await _make_group_event(
        {"id": "guild-1", "name": "Event Name"},
    )
    adapter.logins = [
        {
            "platform": "discord",
            "user": {"id": "bot-1"},
            "features": ["guild.get", "guild.member.list"],
        },
    ]
    list_calls = {"count": 0}

    async def pages(method, path, data, platform, user_id):
        del method, data, platform, user_id
        if path == "/guild.get":
            return {"id": "guild-1", "name": "Fetched Name"}
        list_calls["count"] += 1
        return {
            "data": [
                {
                    "user": {
                        "id": f"user-{list_calls['count']}",
                        "name": f"User {list_calls['count']}",
                    },
                },
            ],
            "next": f"page-{list_calls['count'] + 1}",
        }

    adapter.send_http_request = AsyncMock(side_effect=pages)

    group = await event.get_group()

    assert group is not None
    assert group.group_name == "Fetched Name"
    assert group.members is None
    assert group.member_count is None
    assert list_calls["count"] == 10
    assert [
        call_args.args[1]
        for call_args in adapter.send_http_request.await_args_list
        if call_args.args[1] == "/guild.member.list"
    ] == ["/guild.member.list"] * 10


@pytest.mark.asyncio
async def test_satori_get_group_omits_members_when_first_page_is_over_cap():
    adapter, _, event = await _make_group_event(
        {"id": "guild-1", "name": "Event Name"},
    )
    adapter.logins = [
        {
            "platform": "discord",
            "user": {"id": "bot-1"},
            "features": ["guild.get", "guild.member.list"],
        },
    ]

    async def pages(method, path, data, platform, user_id):
        del method, data, platform, user_id
        if path == "/guild.get":
            return {"id": "guild-1", "name": "Fetched Name"}
        return {
            "data": [
                {"user": {"id": f"user-{index}", "name": f"User {index}"}}
                for index in range(2001)
            ],
            "next": "page-2",
        }

    adapter.send_http_request = AsyncMock(side_effect=pages)

    group = await event.get_group()

    assert group is not None
    assert group.group_name == "Fetched Name"
    assert group.members is None
    assert group.member_count is None
    assert [
        call_args.args[1]
        for call_args in adapter.send_http_request.await_args_list
        if call_args.args[1] == "/guild.member.list"
    ] == ["/guild.member.list"]
