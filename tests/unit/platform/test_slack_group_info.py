import asyncio
from unittest.mock import AsyncMock

import pytest

from astrbot.core.platform import (
    AstrBotMessage,
    Group,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
from astrbot.core.platform.sources.slack.slack_adapter import SlackAdapter
from astrbot.core.platform.sources.slack.slack_event import SlackMessageEvent
from tests.fixtures.helpers import make_platform_config

pytestmark = pytest.mark.platform


def _build_message() -> AstrBotMessage:
    message = AstrBotMessage()
    message.type = MessageType.GROUP_MESSAGE
    message.group = Group(group_id="C123", group_name="cached-channel")
    message.session_id = "C123"
    message.sender = MessageMember(user_id="U1", nickname="Alice")
    message.message_id = "message-1"
    message.message = []
    message.message_str = "hello"
    message.raw_message = {}
    return message


def _platform_metadata() -> PlatformMetadata:
    return PlatformMetadata(name="slack", id="slack", description="Slack")


@pytest.mark.asyncio
async def test_slack_convert_message_includes_channel_name():
    adapter = SlackAdapter(
        make_platform_config(
            "slack",
            id="test_slack",
            bot_token="xoxb-test",
            app_token="xapp-test",
        ),
        {},
        asyncio.Queue(),
    )
    adapter.bot_self_id = "UBOT"
    adapter.web_client.users_info = AsyncMock(
        return_value={"user": {"id": "U1", "real_name": "Alice"}},
    )
    adapter.web_client.conversations_info = AsyncMock(
        return_value={"channel": {"id": "C123", "is_im": False, "name": "general"}},
    )

    message = await adapter.convert_message(
        {"user": "U1", "channel": "C123", "text": "hello", "ts": "1700000000"},
    )

    assert message.group == Group(group_id="C123")


@pytest.mark.asyncio
async def test_slack_convert_message_keeps_group_id_when_channel_lookup_fails():
    adapter = SlackAdapter(
        make_platform_config(
            "slack",
            id="test_slack",
            bot_token="xoxb-test",
            app_token="xapp-test",
        ),
        {},
        asyncio.Queue(),
    )
    adapter.bot_self_id = "UBOT"
    adapter.web_client.users_info = AsyncMock(
        return_value={"user": {"id": "U1", "real_name": "Alice"}},
    )
    adapter.web_client.conversations_info = AsyncMock(
        side_effect=RuntimeError("missing scope"),
    )

    message = await adapter.convert_message(
        {"user": "U1", "channel": "C123", "text": "hello", "ts": "1700000000"},
    )

    assert message.group == Group(group_id="C123")
    assert message.session_id == "C123"


@pytest.mark.asyncio
async def test_slack_get_group_paginates_members_and_does_not_infer_owner():
    web_client = AsyncMock()
    web_client.conversations_info.return_value = {
        "channel": {
            "id": "C123",
            "name": "general",
            "creator": "U0",
            "num_members": 3,
        },
    }
    web_client.conversations_members.side_effect = [
        {
            "members": ["U1", "U2"],
            "response_metadata": {"next_cursor": "next"},
        },
        {"members": ["U3"], "response_metadata": {"next_cursor": ""}},
    ]
    web_client.users_info.side_effect = lambda user: {
        "user": {"id": user, "real_name": f"Name {user}"},
    }
    event = SlackMessageEvent(
        "hello",
        _build_message(),
        platform_meta=_platform_metadata(),
        session_id="C123",
        web_client=web_client,
    )

    group = await event.get_group()

    assert group.group_name == "general"
    assert group.group_owner is None
    assert group.group_avatar is None
    assert group.member_count == 3
    assert [member.user_id for member in group.members] == ["U1", "U2", "U3"]
    assert web_client.conversations_members.await_count == 2


@pytest.mark.asyncio
async def test_slack_get_group_returns_basic_group_when_lookup_fails():
    web_client = AsyncMock()
    web_client.conversations_info.side_effect = RuntimeError("missing scope")
    event = SlackMessageEvent(
        "hello",
        _build_message(),
        platform_meta=_platform_metadata(),
        session_id="C123",
        web_client=web_client,
    )

    group = await event.get_group()

    assert group == Group(group_id="C123", group_name="cached-channel")
