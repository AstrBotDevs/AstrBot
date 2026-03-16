import asyncio
from unittest.mock import AsyncMock

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.slack.session_codec import (
    decode_slack_session_id,
    resolve_slack_message_target,
    resolve_target_from_event,
    resolve_target_from_session,
)
from astrbot.core.platform.sources.slack.slack_adapter import SlackAdapter
from astrbot.core.platform.sources.slack.slack_event import SlackMessageEvent
from astrbot.core.utils.metrics import Metric


@pytest.fixture(autouse=True)
def _disable_metric_upload(monkeypatch):
    monkeypatch.setattr(Metric, "upload", AsyncMock())


@pytest.fixture
def slack_adapter():
    adapter = SlackAdapter(
        platform_config={
            "id": "slack_test",
            "bot_token": "xoxb-test",
            "app_token": "xapp-test",
        },
        platform_settings={},
        event_queue=asyncio.Queue(),
    )
    adapter.bot_self_id = "B0001"
    return adapter


@pytest.mark.asyncio
async def test_convert_message_group_thread_uses_thread_session(slack_adapter):
    slack_adapter.web_client = AsyncMock()
    slack_adapter.web_client.users_info = AsyncMock(
        return_value={"user": {"real_name": "Alice", "name": "alice"}},
    )
    slack_adapter.web_client.conversations_info = AsyncMock(
        return_value={"channel": {"is_im": False}},
    )

    abm = await slack_adapter.convert_message(
        {
            "user": "U0001",
            "channel": "C0001",
            "text": "hello",
            "client_msg_id": "m-1",
            "ts": "1710000001.100",
            "thread_ts": "1710000000.500",
        },
    )

    assert abm.type == MessageType.GROUP_MESSAGE
    assert abm.group_id == "C0001"
    assert abm.session_id == "C0001__thread__1710000000.500"


@pytest.mark.asyncio
async def test_convert_message_friend_thread_uses_thread_session(slack_adapter):
    slack_adapter.web_client = AsyncMock()
    slack_adapter.web_client.users_info = AsyncMock(
        return_value={"user": {"real_name": "Alice", "name": "alice"}},
    )
    slack_adapter.web_client.conversations_info = AsyncMock(
        return_value={"channel": {"is_im": True}},
    )

    abm = await slack_adapter.convert_message(
        {
            "user": "U0001",
            "channel": "D0001",
            "text": "hello in dm thread",
            "client_msg_id": "m-friend-1",
            "ts": "1710000010.100",
            "thread_ts": "1710000009.500",
        },
    )

    assert abm.type == MessageType.FRIEND_MESSAGE
    assert abm.session_id == "D0001__thread__1710000009.500"


@pytest.mark.asyncio
async def test_convert_message_unwraps_message_replied_event(slack_adapter):
    slack_adapter.web_client = AsyncMock()
    slack_adapter.web_client.users_info = AsyncMock(
        return_value={"user": {"real_name": "Alice", "name": "alice"}},
    )
    slack_adapter.web_client.conversations_info = AsyncMock(
        return_value={"channel": {"is_im": False}},
    )

    abm = await slack_adapter.convert_message(
        {
            "type": "message",
            "subtype": "message_replied",
            "channel": "C0001",
            "message": {
                "user": "U0001",
                "text": "reply",
                "ts": "1710000200.001",
                "thread_ts": "1710000000.500",
                "client_msg_id": "m-replied-1",
            },
        },
    )

    assert abm.sender.user_id == "U0001"
    assert abm.message_str == "reply"
    assert abm.session_id == "C0001__thread__1710000000.500"


@pytest.mark.asyncio
async def test_send_by_session_group_thread_posts_with_thread_ts(slack_adapter, monkeypatch):
    slack_adapter.web_client = AsyncMock()
    monkeypatch.setattr(
        SlackMessageEvent,
        "_parse_slack_blocks",
        AsyncMock(return_value=([], "reply")),
    )
    session = MessageSession(
        platform_name="slack_test",
        message_type=MessageType.GROUP_MESSAGE,
        session_id="C0001__thread__1710000000.500",
    )

    await slack_adapter.send_by_session(
        session=session,
        message_chain=MessageChain([Plain(text="reply")]),
    )

    slack_adapter.web_client.chat_postMessage.assert_awaited_once_with(
        channel="C0001",
        text="reply",
        blocks=None,
        thread_ts="1710000000.500",
    )


@pytest.mark.asyncio
async def test_send_by_session_friend_thread_posts_with_thread_ts(slack_adapter, monkeypatch):
    slack_adapter.web_client = AsyncMock()
    monkeypatch.setattr(
        SlackMessageEvent,
        "_parse_slack_blocks",
        AsyncMock(return_value=([], "reply")),
    )
    session = MessageSession(
        platform_name="slack_test",
        message_type=MessageType.FRIEND_MESSAGE,
        session_id="D0001__thread__1710000000.500",
    )

    await slack_adapter.send_by_session(
        session=session,
        message_chain=MessageChain([Plain(text="reply")]),
    )

    slack_adapter.web_client.chat_postMessage.assert_awaited_once_with(
        channel="D0001",
        text="reply",
        blocks=None,
        thread_ts="1710000000.500",
    )


@pytest.mark.asyncio
async def test_slack_event_send_group_thread_posts_with_thread_ts(monkeypatch):
    message_obj = AstrBotMessage()
    message_obj.type = MessageType.GROUP_MESSAGE
    message_obj.group_id = "C0001"
    message_obj.session_id = "C0001__thread__1710000000.500"
    message_obj.message_id = "m-2"
    message_obj.sender = MessageMember(user_id="U0001", nickname="Alice")
    message_obj.message = [Plain(text="hello")]
    message_obj.message_str = "hello"
    message_obj.raw_message = {"thread_ts": "1710000000.500"}

    web_client = AsyncMock()
    monkeypatch.setattr(
        SlackMessageEvent,
        "_parse_slack_blocks",
        AsyncMock(return_value=([], "reply")),
    )

    event = SlackMessageEvent(
        message_str=message_obj.message_str,
        message_obj=message_obj,
        platform_meta=PlatformMetadata(
            name="slack",
            description="Slack test",
            id="slack_test",
        ),
        session_id=message_obj.session_id,
        web_client=web_client,
    )

    await event.send(MessageChain([Plain(text="reply")]))

    web_client.chat_postMessage.assert_awaited_once_with(
        channel="C0001",
        text="reply",
        blocks=None,
        thread_ts="1710000000.500",
    )


@pytest.mark.asyncio
async def test_slack_event_send_friend_thread_posts_with_thread_ts(monkeypatch):
    message_obj = AstrBotMessage()
    message_obj.type = MessageType.FRIEND_MESSAGE
    message_obj.session_id = "D0001__thread__1710000000.500"
    message_obj.message_id = "m-friend-2"
    message_obj.sender = MessageMember(user_id="U0001", nickname="Alice")
    message_obj.message = [Plain(text="hello")]
    message_obj.message_str = "hello"
    message_obj.raw_message = {"channel": "D0001", "thread_ts": "1710000000.500"}

    web_client = AsyncMock()
    monkeypatch.setattr(
        SlackMessageEvent,
        "_parse_slack_blocks",
        AsyncMock(return_value=([], "reply")),
    )

    event = SlackMessageEvent(
        message_str=message_obj.message_str,
        message_obj=message_obj,
        platform_meta=PlatformMetadata(
            name="slack",
            description="Slack test",
            id="slack_test",
        ),
        session_id=message_obj.session_id,
        web_client=web_client,
    )

    await event.send(MessageChain([Plain(text="reply")]))

    web_client.chat_postMessage.assert_awaited_once_with(
        channel="D0001",
        text="reply",
        blocks=None,
        thread_ts="1710000000.500",
    )


@pytest.mark.asyncio
async def test_parse_slack_blocks_includes_non_empty_fallback_text():
    blocks, text = await SlackMessageEvent._parse_slack_blocks(
        MessageChain([Plain(text="hello")]),
        AsyncMock(),
    )

    assert blocks
    assert text == "hello"


def test_decode_slack_session_id_thread_marker_does_not_fallback_to_legacy():
    channel_id, thread_ts = decode_slack_session_id("C123__thread__")

    assert channel_id == "C123"
    assert thread_ts is None


def test_decode_slack_session_id_supports_legacy_group_prefix():
    channel_id, thread_ts = decode_slack_session_id("group_C123")

    assert channel_id == "C123"
    assert thread_ts is None


def test_resolve_slack_message_target_prefers_raw_message_thread_ts():
    channel_id, thread_ts = resolve_slack_message_target(
        session_id="C123__thread__111.222",
        raw_message={"channel": "C123", "thread_ts": "333.444"},
        group_id="",
        sender_id="U123",
    )

    assert channel_id == "C123"
    assert thread_ts == "333.444"


def test_resolve_target_from_event_prefers_raw_thread_and_group_precedence():
    channel_id, thread_ts = resolve_target_from_event(
        session_id="C123__thread__111.222",
        raw_message={"channel": "C333", "thread_ts": "333.444"},
        group_id="C999",
    )

    assert channel_id == "C999"
    assert thread_ts == "333.444"


def test_resolve_target_from_session_uses_parsed_thread():
    channel_id, thread_ts = resolve_target_from_session(
        session_id="D123__thread__1710000000.500",
    )

    assert channel_id == "D123"
    assert thread_ts == "1710000000.500"
