import json
from unittest.mock import AsyncMock

import pytest

from astrbot.api.platform import PlatformMetadata, Unknown
from astrbot.core.message.components import (
    At,
    AtAll,
    BaseMessageComponent,
    Image,
    Json,
    Plain,
    Reply,
    Video,
)
from astrbot.core.platform.astrbot_message import AstrBotMessage, Group
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.sources.kook.kook_event import KookEvent
from astrbot.core.platform.sources.kook.kook_types import KookMessageType, OrderMessage
from tests.unit.platform.kook.shared import (
    mock_astrbot_message,
    mock_file_message,
    mock_kook_client,
    mock_record_message,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "input_message,upload_asset_return, expected_output, expected_error",
    [
        (
            Image(file="test image"),
            "test image",
            OrderMessage(
                index=1,
                text="test image",
                type=KookMessageType.IMAGE,
            ),
            None,
        ),
        (
            Video(file="test video"),
            "test video",
            OrderMessage(
                index=1,
                text="test video",
                type=KookMessageType.VIDEO,
            ),
            None,
        ),
        (
            mock_file_message("test file"),
            "test file",
            OrderMessage(
                index=1,
                text="test file",
                type=KookMessageType.FILE,
            ),
            None,
        ),
        (
            mock_record_message("./tests/file.wav"),
            "./tests/file.wav",
            OrderMessage(
                index=1,
                text='[{"type": "card", "modules": [{"type": "audio", "src": "./tests/file.wav", "title": "./tests/file.wav"}]}]',
                type=KookMessageType.CARD,
            ),
            None,
        ),
        (
            Plain("test plain"),
            "test plain",
            OrderMessage(
                index=1,
                text="test plain",
                type=KookMessageType.KMARKDOWN,
            ),
            None,
        ),
        (
            At(qq="test at"),
            "test at",
            OrderMessage(
                index=1,
                text="(met)test at(met)",
                type=KookMessageType.KMARKDOWN,
            ),
            None,
        ),
        (
            AtAll(qq="all"),
            "test atAll",
            OrderMessage(
                index=1,
                text="(met)all(met)",
                type=KookMessageType.KMARKDOWN,
            ),
            None,
        ),
        (
            Reply(id="test reply"),
            "test reply",
            OrderMessage(
                index=1,
                text="",
                type=KookMessageType.KMARKDOWN,
                reply_id="test reply",
            ),
            None,
        ),
        (
            Json(data={"test": "json"}),
            "test json",
            OrderMessage(
                index=1,
                text='[{"test": "json"}]',
                type=KookMessageType.CARD,
            ),
            None,
        ),
        (
            Unknown(text="test unknown"),
            "test unknown",
            None,
            NotImplementedError,
        ),
    ],
)
async def test_kook_event_warp_message(
    input_message: BaseMessageComponent,
    upload_asset_return: str,
    expected_output: OrderMessage,
    expected_error: type[BaseException] | None,
):
    client = mock_kook_client(
        upload_asset_return,
        "",
    )

    event = KookEvent(
        "",
        mock_astrbot_message(),
        PlatformMetadata(
            name="test",
            id="test",
            description="test",
        ),
        "",
        client,
    )

    if expected_error:
        with pytest.raises(expected_error):
            await event._wrap_message(1, input_message)
        return

    result = await event._wrap_message(1, input_message)

    expected_output_text: str | list | dict = expected_output.text
    is_json_text = False
    try:
        expected_output_text = json.loads(expected_output_text)
        is_json_text = True
    except TypeError, json.JSONDecodeError:
        pass

    if is_json_text:
        assert json.loads(result.text) == expected_output_text
    else:
        assert result.text == expected_output_text

    assert result.index == expected_output.index
    assert result.type == expected_output.type
    assert result.reply_id == expected_output.reply_id


def test_kook_create_event_does_not_promote_guild_roles():
    from types import SimpleNamespace

    from astrbot.core.platform.sources.kook.kook_adapter import KookPlatformAdapter

    adapter = KookPlatformAdapter.__new__(KookPlatformAdapter)
    adapter.kook_config = SimpleNamespace(id="kook-test")
    adapter.client = SimpleNamespace()
    message = mock_astrbot_message()
    message.message_str = "hello"
    message.message = []
    message.raw_message = SimpleNamespace(
        extra=SimpleNamespace(author=SimpleNamespace(roles=[1, 2]))
    )
    event = adapter.create_event(message)
    assert event.platform_member_role == "member"
    assert event.platform_role_source == "none"


@pytest.mark.asyncio
async def test_kook_get_group_enriches_channel_with_guild_members():
    client = mock_kook_client("", "")
    client.get_channel = AsyncMock(
        return_value={"id": "channel-1", "name": "general", "guild_id": "guild-1"},
    )
    client.get_guild = AsyncMock(
        return_value={
            "id": "guild-1",
            "icon": "https://example.com/icon.png",
            "user_id": "owner-1",
        },
    )
    client.get_guild_roles = AsyncMock(
        return_value={
            "items": [
                {"role_id": 1, "permissions": 1},
                {"role_id": 2, "permissions": 0},
            ],
            "meta": {"page_total": 1, "total": 2},
        },
    )
    client.get_guild_users = AsyncMock(
        side_effect=[
            {
                "items": [
                    {"id": "owner-1", "nickname": "Owner", "roles": [1]},
                    {"id": "user-1", "username": "Alice", "roles": [2]},
                ],
                "meta": {"page_total": 2, "total": 3},
            },
            {
                "items": [{"id": "user-2", "username": "Bob", "roles": [1]}],
                "meta": {"page_total": 2, "total": 3},
            },
        ],
    )
    message = AstrBotMessage()
    message.type = MessageType.GROUP_MESSAGE
    inbound = Group(group_id="channel-1", group_name="cached-channel")
    message.group = inbound
    message.session_id = "channel-1"
    message.message_id = "message-1"
    message.message = []
    message.message_str = "hello"
    message.raw_message = {"extra": {"guild_id": "guild-1"}}
    event = KookEvent(
        "hello",
        message,
        PlatformMetadata(name="kook", id="kook", description="KOOK"),
        "channel-1",
        client,
    )

    group = await event.get_group()

    assert group is not inbound
    assert group.group_name == "general"
    assert group.group_avatar == "https://example.com/icon.png"
    assert group.group_owner == "owner-1"
    assert group.member_count == 3
    assert [member.user_id for member in group.members] == [
        "owner-1",
        "user-1",
        "user-2",
    ]
    assert group.group_admins == ["owner-1", "user-2"]
    assert inbound.members is None
    assert client.get_guild_users.await_count == 2
    client.get_guild_users.assert_any_await(
        "guild-1",
        channel_id="channel-1",
        page=1,
        page_size=50,
    )
    client.get_guild_roles.assert_awaited_once_with(
        "guild-1",
        page=1,
        page_size=50,
    )


@pytest.mark.asyncio
async def test_kook_get_group_returns_basic_group_when_lookup_fails():
    client = mock_kook_client("", "")
    client.get_channel = AsyncMock(side_effect=RuntimeError("forbidden"))
    message = AstrBotMessage()
    message.type = MessageType.GROUP_MESSAGE
    inbound = Group(group_id="channel-1", group_name="cached-channel")
    message.group = inbound
    message.session_id = "channel-1"
    message.message_id = "message-1"
    message.message = []
    message.message_str = "hello"
    message.raw_message = {}
    event = KookEvent(
        "hello",
        message,
        PlatformMetadata(name="kook", id="kook", description="KOOK"),
        "channel-1",
        client,
    )

    group = await event.get_group()

    assert group is not inbound
    assert group == Group(group_id="channel-1", group_name="cached-channel")


@pytest.mark.asyncio
async def test_kook_get_group_caps_member_pages_and_omits_truncated_list():
    client = mock_kook_client("", "")
    client.get_channel = AsyncMock(
        return_value={"id": "channel-1", "name": "general", "guild_id": "guild-1"},
    )
    client.get_guild = AsyncMock(
        return_value={"id": "guild-1", "icon": None, "user_id": "owner-1"},
    )
    client.get_guild_roles = AsyncMock(return_value={"items": [], "meta": {}})

    async def endless_members(guild_id, *, channel_id, page, page_size):
        del guild_id, channel_id, page_size
        return {
            "items": [{"id": f"user-{page}", "username": f"User {page}", "roles": []}],
            "meta": {"page_total": 20, "total": 2500},
        }

    client.get_guild_users = AsyncMock(side_effect=endless_members)
    message = AstrBotMessage()
    message.type = MessageType.GROUP_MESSAGE
    message.group = Group(group_id="channel-1")
    message.session_id = "channel-1"
    message.message_id = "message-1"
    message.message = []
    message.message_str = "hello"
    message.raw_message = {}
    event = KookEvent(
        "hello",
        message,
        PlatformMetadata(name="kook", id="kook", description="KOOK"),
        "channel-1",
        client,
    )

    group = await event.get_group()

    assert group.member_count == 2500
    assert group.members is None
    assert client.get_guild_users.await_count == 10
