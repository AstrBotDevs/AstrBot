import asyncio
from unittest.mock import AsyncMock

import pytest

from astrbot.api.message_components import (
    ActionRow,
    Button,
    ButtonInteraction,
    CallbackAction,
    UrlAction,
)
from astrbot.core.platform.button_interaction import (
    decode_button_callback,
    encode_button_callback,
)
from astrbot.core.platform.sources.line.line_adapter import LinePlatformAdapter
from astrbot.core.platform.sources.line.line_event import LineMessageEvent
from astrbot.core.platform.sources.line.line_api import LineAPIClient
from tests.fixtures.helpers import make_platform_config


def _build_adapter() -> LinePlatformAdapter:
    """Build a LINE adapter without making network requests.

    Returns:
        Configured LINE platform adapter.
    """
    return LinePlatformAdapter(
        make_platform_config(
            "line",
            channel_access_token="test-token",
            channel_secret="test-secret",
        ),
        {},
        asyncio.Queue(),
    )


@pytest.mark.asyncio
async def test_line_action_row_builds_template_actions():
    row = ActionRow(
        fallback_text="Choose an action",
        buttons=[
            Button(
                id="approve",
                label="Approve",
                action=CallbackAction(data={"request_id": 42}),
            ),
            Button(
                id="docs",
                label="Documentation",
                action=UrlAction(url="https://example.com/docs"),
            ),
        ],
    )

    message = await LineMessageEvent._component_to_message_object(row)

    assert message is not None
    assert message["type"] == "template"
    assert message["altText"] == "Choose an action"
    actions = message["template"]["actions"]
    assert actions[1] == {
        "type": "uri",
        "label": "Documentation",
        "uri": "https://example.com/docs",
    }
    action_id, data = decode_button_callback(actions[0]["data"])
    assert action_id == "approve"
    assert data == {"request_id": 42}


@pytest.mark.asyncio
async def test_line_action_row_uses_compact_postback_token_for_large_data():
    row = ActionRow(
        buttons=[
            Button(
                id="oversized",
                label="Oversized",
                action=CallbackAction(data={"value": "x" * 300}),
            )
        ]
    )

    message = await LineMessageEvent._component_to_message_object(row)

    callback_data = message["template"]["actions"][0]["data"]
    assert len(callback_data.encode("utf-8")) <= 300
    assert decode_button_callback(callback_data) == (
        "oversized",
        {"value": "x" * 300},
    )


@pytest.mark.asyncio
async def test_line_postback_becomes_button_interaction():
    adapter = _build_adapter()
    callback_data = encode_button_callback("approve", {"request_id": 42})

    message = await adapter.convert_message(
        {
            "type": "postback",
            "mode": "active",
            "timestamp": 1_700_000_000_000,
            "webhookEventId": "event-1",
            "source": {"type": "group", "groupId": "group-1", "userId": "user-1"},
            "postback": {"data": callback_data},
        }
    )

    assert message is not None
    assert message.message_id == "event-1"
    assert message.session_id == "group-1"
    assert len(message.message) == 1
    interaction = message.message[0]
    assert isinstance(interaction, ButtonInteraction)
    assert interaction.action_id == "approve"
    assert interaction.data == {"request_id": 42}
    assert interaction.interaction_id == "event-1"
    event = adapter.create_event(message)
    assert event.is_button_interaction()
    assert event.get_button_interaction() is interaction


@pytest.mark.asyncio
async def test_line_ignores_foreign_postback_payload():
    adapter = _build_adapter()

    message = await adapter.convert_message(
        {
            "type": "postback",
            "source": {"type": "user", "userId": "user-1"},
            "postback": {"data": "third-party=value"},
        }
    )

    assert message is None


def _group_message(source: dict) -> dict:
    """Build a minimal LINE text message webhook event.

    Args:
        source: LINE webhook source object.

    Returns:
        LINE webhook message event.
    """
    return {
        "type": "message",
        "mode": "active",
        "timestamp": 1_700_000_000_000,
        "webhookEventId": "event-1",
        "source": source,
        "message": {"id": "message-1", "type": "text", "text": "hello"},
    }


@pytest.mark.asyncio
async def test_line_group_message_carries_available_basic_group_information():
    adapter = _build_adapter()

    result = await adapter.convert_message(
        _group_message(
            {
                "type": "group",
                "groupId": "C-group",
                "userId": "U-sender",
                "groupName": "Webhook group",
                "pictureUrl": "https://example.com/group.png",
            }
        )
    )

    assert result is not None
    assert result.group is not None
    assert result.group.group_id == "C-group"
    assert result.group.group_name == "Webhook group"
    assert result.group.group_avatar == "https://example.com/group.png"


@pytest.mark.asyncio
async def test_line_group_message_does_not_use_group_id_as_name():
    adapter = _build_adapter()

    result = await adapter.convert_message(
        _group_message(
            {
                "type": "group",
                "groupId": "C-group",
                "userId": "U-sender",
            }
        )
    )

    assert result is not None
    assert result.group is not None
    assert result.group.group_id == "C-group"
    assert result.group.group_name is None


@pytest.mark.asyncio
async def test_line_get_group_enriches_summary_count_and_members():
    adapter = _build_adapter()
    message = await adapter.convert_message(
        _group_message(
            {
                "type": "group",
                "groupId": "C-group",
                "userId": "U-sender",
            }
        )
    )
    assert message is not None

    adapter.line_api.get_group_summary = AsyncMock(
        return_value={
            "groupId": "C-group",
            "groupName": "LINE group",
            "pictureUrl": "https://example.com/group.png",
        }
    )
    adapter.line_api.get_chat_member_count = AsyncMock(return_value=2)
    adapter.line_api.get_chat_member_ids = AsyncMock(return_value=["U-one", "U-two"])
    adapter.line_api.get_chat_member_profile = AsyncMock(
        side_effect=[
            {"userId": "U-one", "displayName": "Alice"},
            None,
        ]
    )

    result = await adapter.create_event(message).get_group()

    assert result is not None
    assert result.group_id == "C-group"
    assert result.group_name == "LINE group"
    assert result.group_avatar == "https://example.com/group.png"
    assert result.member_count == 2
    assert result.members is not None
    assert [(member.user_id, member.nickname) for member in result.members] == [
        ("U-one", "Alice"),
        ("U-two", None),
    ]
    adapter.line_api.get_chat_member_count.assert_awaited_once_with("group", "C-group")


@pytest.mark.asyncio
async def test_line_get_room_uses_room_endpoints_without_summary():
    adapter = _build_adapter()
    message = await adapter.convert_message(
        _group_message(
            {
                "type": "room",
                "roomId": "R-room",
                "userId": "U-sender",
            }
        )
    )
    assert message is not None

    adapter.line_api.get_group_summary = AsyncMock()
    adapter.line_api.get_chat_member_count = AsyncMock(return_value=3)
    adapter.line_api.get_chat_member_ids = AsyncMock(return_value=None)
    adapter.line_api.get_chat_member_profile = AsyncMock()

    result = await adapter.create_event(message).get_group()

    assert result is not None
    assert result.group_id == "R-room"
    assert result.group_name is None
    assert result.member_count == 3
    assert result.members is None
    adapter.line_api.get_group_summary.assert_not_awaited()
    adapter.line_api.get_chat_member_count.assert_awaited_once_with("room", "R-room")
    adapter.line_api.get_chat_member_profile.assert_not_awaited()


@pytest.mark.asyncio
async def test_line_get_group_returns_basic_information_when_api_calls_fail():
    adapter = _build_adapter()
    message = await adapter.convert_message(
        _group_message(
            {
                "type": "group",
                "groupId": "C-group",
                "userId": "U-sender",
                "groupName": "Webhook group",
            }
        )
    )
    assert message is not None

    adapter.line_api.get_group_summary = AsyncMock(side_effect=RuntimeError("denied"))
    adapter.line_api.get_chat_member_count = AsyncMock(
        side_effect=RuntimeError("denied")
    )
    adapter.line_api.get_chat_member_ids = AsyncMock(side_effect=RuntimeError("denied"))

    result = await adapter.create_event(message).get_group()

    assert result is not None
    assert result.group_id == "C-group"
    assert result.group_name == "Webhook group"
    assert result.member_count is None
    assert result.members is None


@pytest.mark.asyncio
async def test_line_member_id_api_follows_pagination_tokens():
    client = LineAPIClient(
        channel_access_token="test-token",
        channel_secret="test-secret",
    )
    client._get_json = AsyncMock(
        side_effect=[
            {"memberIds": ["U-one"], "next": "next-page"},
            {"memberIds": ["U-two", "U-one"]},
        ]
    )

    result = await client.get_chat_member_ids("group", "C-group")

    assert result == ["U-one", "U-two"]
    assert client._get_json.await_count == 2
    assert client._get_json.await_args_list[0].kwargs["params"] is None
    assert client._get_json.await_args_list[1].kwargs["params"] == {
        "start": "next-page"
    }


@pytest.mark.asyncio
async def test_line_member_id_api_returns_none_when_restricted():
    client = LineAPIClient(
        channel_access_token="test-token",
        channel_secret="test-secret",
    )
    client._get_json = AsyncMock(return_value=None)

    result = await client.get_chat_member_ids("room", "R-room")

    assert result is None
