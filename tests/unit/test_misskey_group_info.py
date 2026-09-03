import asyncio
from unittest.mock import AsyncMock

import pytest

from astrbot.core.platform.sources.misskey.misskey_adapter import (
    MisskeyPlatformAdapter,
)

pytestmark = pytest.mark.platform


def make_adapter() -> MisskeyPlatformAdapter:
    """Create a Misskey adapter suitable for message conversion tests.

    Returns:
        Adapter with an in-memory event queue and no network client.
    """
    adapter = MisskeyPlatformAdapter(
        {"id": "misskey-test"},
        {},
        asyncio.Queue(),
    )
    adapter.bot_self_id = "bot-id"
    return adapter


@pytest.mark.asyncio
async def test_room_message_maps_embedded_room_information() -> None:
    adapter = make_adapter()

    message = await adapter.convert_room_message(
        {
            "id": "message-1",
            "text": "hello",
            "fromUserId": "sender-id",
            "fromUser": {"id": "sender-id", "username": "sender"},
            "toRoomId": "room-id",
            "toRoom": {
                "id": "room-id",
                "name": "AstrBot room",
                "ownerId": "owner-id",
            },
        },
    )

    assert message.group is not None
    assert message.group.group_id == "room-id"
    assert message.group.group_name == "AstrBot room"
    assert message.group.group_owner == "owner-id"


@pytest.mark.asyncio
async def test_get_group_paginates_members_and_adds_owner() -> None:
    adapter = make_adapter()
    message = await adapter.convert_room_message(
        {
            "id": "message-1",
            "text": "hello",
            "fromUserId": "sender-id",
            "fromUser": {"id": "sender-id", "username": "sender"},
            "toRoomId": "room-id",
            "toRoom": {"name": "Cached room", "ownerId": "owner-id"},
        },
    )
    first_page = [
        {
            "id": f"membership-{index}",
            "userId": f"user-{index}",
            "user": {"id": f"user-{index}", "username": f"user{index}"},
        }
        for index in range(100)
    ]
    second_page = [
        {
            "id": "membership-100",
            "userId": "user-100",
            "user": {"id": "user-100", "name": "Last member"},
        },
    ]
    assert message.group is not None
    message.group.group_avatar = "https://example.com/room.png"
    adapter.api = AsyncMock()
    adapter.api._make_request = AsyncMock(
        side_effect=[
            {
                "id": "room-id",
                "name": "Current room",
                "ownerId": "owner-id",
                "owner": {"id": "owner-id", "name": "Room owner"},
            },
            first_page,
            second_page,
        ],
    )

    group = await adapter.create_event(message).get_group()

    assert group is not None
    assert group is not message.group
    assert message.group.members is None
    assert group.group_name == "Current room"
    assert group.group_owner == "owner-id"
    assert group.group_avatar == "https://example.com/room.png"
    assert group.group_admins == []
    assert group.member_count == 102
    assert group.members is not None
    assert group.members[-1].user_id == "owner-id"
    assert group.members[-1].nickname == "Room owner"
    assert adapter.api._make_request.await_args_list[2].args == (
        "chat/rooms/members",
        {
            "roomId": "room-id",
            "limit": 100,
            "untilId": "membership-99",
        },
    )


@pytest.mark.asyncio
async def test_get_group_falls_back_when_room_api_is_unavailable() -> None:
    adapter = make_adapter()
    message = await adapter.convert_room_message(
        {
            "id": "message-1",
            "text": "hello",
            "fromUserId": "sender-id",
            "fromUser": {"id": "sender-id", "username": "sender"},
            "toRoomId": "room-id",
            "toRoom": {"name": "Cached room", "ownerId": "owner-id"},
        },
    )
    adapter.api = AsyncMock()
    adapter.api._make_request = AsyncMock(side_effect=RuntimeError("not supported"))

    group = await adapter.create_event(message).get_group()

    assert group is not None
    assert group.group_id == "room-id"
    assert group.group_name == "Cached room"
    assert group.group_owner == "owner-id"
    assert group.members is None


@pytest.mark.asyncio
async def test_get_group_caps_member_pages_and_omits_truncated_list() -> None:
    adapter = make_adapter()
    message = await adapter.convert_room_message(
        {
            "id": "message-1",
            "text": "hello",
            "fromUserId": "sender-id",
            "fromUser": {"id": "sender-id", "username": "sender"},
            "toRoomId": "room-id",
            "toRoom": {"name": "Cached room", "ownerId": "owner-id"},
        },
    )
    assert message.group is not None
    message.group.group_avatar = "https://example.com/room.png"
    message.group.member_count = 42
    member_calls = {"count": 0}

    async def pages(endpoint, payload):
        del payload
        if endpoint == "chat/rooms/show":
            return {
                "id": "room-id",
                "name": "Current room",
                "ownerId": "owner-id",
                "owner": {"id": "owner-id", "name": "Room owner"},
            }
        member_calls["count"] += 1
        page = member_calls["count"]
        return [
            {
                "id": f"membership-{page}-{index}",
                "userId": f"user-{page}-{index}",
                "user": {
                    "id": f"user-{page}-{index}",
                    "username": f"user{index}",
                },
            }
            for index in range(100)
        ]

    adapter.api = AsyncMock()
    adapter.api._make_request = AsyncMock(side_effect=pages)

    group = await adapter.create_event(message).get_group()

    assert group is not None
    assert group.group_name == "Current room"
    assert group.group_owner == "owner-id"
    assert group.group_avatar == "https://example.com/room.png"
    assert group.members is None
    assert group.member_count == 42
    assert member_calls["count"] == 10
    assert [
        call_args.args[0]
        for call_args in adapter.api._make_request.await_args_list
        if call_args.args[0] == "chat/rooms/members"
    ] == ["chat/rooms/members"] * 10


def _memberships(count: int, *, prefix: str = "user") -> list[dict]:
    return [
        {
            "id": f"membership-{index}",
            "userId": f"{prefix}-{index}",
            "user": {"id": f"{prefix}-{index}", "username": f"{prefix}{index}"},
        }
        for index in range(count)
    ]


@pytest.mark.asyncio
async def test_get_group_omits_members_when_first_page_is_over_cap() -> None:
    adapter = make_adapter()
    message = await adapter.convert_room_message(
        {
            "id": "message-1",
            "text": "hello",
            "fromUserId": "sender-id",
            "fromUser": {"id": "sender-id", "username": "sender"},
            "toRoomId": "room-id",
            "toRoom": {"name": "Cached room", "ownerId": "owner-id"},
        },
    )
    adapter.api = AsyncMock()
    adapter.api._make_request = AsyncMock(
        side_effect=[
            {
                "id": "room-id",
                "name": "Current room",
                "ownerId": "owner-id",
                "owner": {"id": "owner-id", "name": "Room owner"},
            },
            _memberships(2001),
        ],
    )

    group = await adapter.create_event(message).get_group()

    assert group is not None
    assert group.group_name == "Current room"
    assert group.group_owner == "owner-id"
    assert group.members is None
    assert group.member_count is None
    assert adapter.api._make_request.await_args_list[1].args == (
        "chat/rooms/members",
        {"roomId": "room-id", "limit": 100},
    )
    assert [
        call_args.args[0]
        for call_args in adapter.api._make_request.await_args_list
        if call_args.args[0] == "chat/rooms/members"
    ] == ["chat/rooms/members"]


@pytest.mark.asyncio
async def test_get_group_omits_members_when_owner_append_exceeds_cap() -> None:
    adapter = make_adapter()
    message = await adapter.convert_room_message(
        {
            "id": "message-1",
            "text": "hello",
            "fromUserId": "sender-id",
            "fromUser": {"id": "sender-id", "username": "sender"},
            "toRoomId": "room-id",
            "toRoom": {"name": "Cached room", "ownerId": "owner-id"},
        },
    )
    adapter.api = AsyncMock()
    adapter.api._make_request = AsyncMock(
        side_effect=[
            {
                "id": "room-id",
                "name": "Current room",
                "ownerId": "owner-id",
                "owner": {"id": "owner-id", "name": "Room owner"},
            },
            _memberships(2000),
            [],
        ],
    )

    group = await adapter.create_event(message).get_group()

    assert group is not None
    assert group.group_name == "Current room"
    assert group.group_owner == "owner-id"
    assert group.group_admins == []
    assert group.members is None
    assert group.member_count == 2001
    assert [
        call_args.args[0]
        for call_args in adapter.api._make_request.await_args_list
        if call_args.args[0] == "chat/rooms/members"
    ] == ["chat/rooms/members"] * 2
