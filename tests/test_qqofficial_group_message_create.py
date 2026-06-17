import asyncio
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import botpy
import botpy.message
import pytest
from botpy import ConnectionSession

from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, Plain
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    QQOfficialPlatformAdapter,
    _ensure_group_message_create_parser,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    botClient as QQOfficialBotClient,
)
from astrbot.core.platform.sources.qqofficial_webhook.qo_webhook_adapter import (
    QQOfficialWebhookPlatformAdapter,
)


def _make_group_payload(
    *,
    message_id: str = "msg-1",
    content: str = "hello world",
    mentions: list[dict] | None = None,
    member_openid: str = "member-1",
    group_openid: str = "group-1",
) -> dict:
    return {
        "id": f"event-{message_id}",
        "d": {
            "id": message_id,
            "content": content,
            "author": {"member_openid": member_openid},
            "group_openid": group_openid,
            "mentions": mentions or [],
            "attachments": [],
        },
    }


def _dispatch_group_message(payload: dict) -> tuple[str, botpy.message.GroupMessage]:
    dispatched: list[tuple[str, botpy.message.GroupMessage]] = []
    _ensure_group_message_create_parser()
    connection = ConnectionSession(
        max_async=1,
        connect=lambda: None,
        dispatch=lambda event, message: dispatched.append((event, message)),
        loop=asyncio.get_event_loop(),
        api=None,
    )
    connection.parser["group_message_create"](payload)
    return dispatched[0]


@pytest.mark.asyncio
async def test_group_message_create_parser_is_registered_and_dispatches_group_message():
    QQOfficialPlatformAdapter(
        {
            "id": "qq-official-test",
            "appid": "123",
            "secret": "secret",
            "enable_group_c2c": True,
            "enable_guild_direct_message": False,
        },
        {},
        asyncio.Queue(),
    )

    event_name, message = _dispatch_group_message(_make_group_payload())

    assert event_name == "group_message_create"
    assert isinstance(message, botpy.message.GroupMessage)
    assert message.group_openid == "group-1"


@pytest.mark.asyncio
async def test_parse_group_message_create_plain_message_has_no_at_component():
    _, message = _dispatch_group_message(
        _make_group_payload(content="plain group message")
    )

    abm = await QQOfficialPlatformAdapter._parse_from_qqofficial(
        message,
        MessageType.GROUP_MESSAGE,
    )

    assert abm.type == MessageType.GROUP_MESSAGE
    assert abm.sender.user_id == "member-1"
    assert abm.group_id == "group-1"
    assert abm.message_str == "plain group message"
    assert not any(isinstance(component, At) for component in abm.message)
    assert [
        component.text for component in abm.message if isinstance(component, Plain)
    ] == ["plain group message"]


@pytest.mark.asyncio
async def test_parse_group_message_create_bot_mention_cleans_plain_text():
    _, message = _dispatch_group_message(
        _make_group_payload(
            content="<@!bot-123> hello there",
            mentions=[{"id": "bot-123", "is_you": True}],
        )
    )

    abm = await QQOfficialPlatformAdapter._parse_from_qqofficial(
        message,
        MessageType.GROUP_MESSAGE,
    )

    assert isinstance(abm.message[0], At)
    assert abm.message[0].qq == "bot-123"
    assert abm.self_id == "bot-123"
    assert isinstance(abm.message[1], Plain)
    assert abm.message[1].text == "hello there"
    assert abm.message_str == "hello there"
    assert abm.sender.user_id == "member-1"
    assert abm.group_id == "group-1"


@pytest.mark.asyncio
async def test_legacy_group_at_path_forces_bot_mention_when_mentions_missing():
    message = botpy.message.GroupMessage(
        None,
        "event-legacy",
        _make_group_payload(content="legacy text", mentions=[])["d"],
    )

    abm = await QQOfficialPlatformAdapter._parse_from_qqofficial(
        message,
        MessageType.GROUP_MESSAGE,
        force_group_mention=True,
    )

    assert isinstance(abm.message[0], At)
    assert abm.message[0].qq == "qq_official"
    assert abm.self_id == "qq_official"
    assert isinstance(abm.message[1], Plain)
    assert abm.message[1].text == "legacy text"


@pytest.mark.asyncio
async def test_group_message_create_handler_maps_group_session_and_scene():
    _, message = _dispatch_group_message(_make_group_payload())
    committed: list = []
    remembered_scenes: list[tuple[str, str]] = []
    remembered_ids: list[tuple[str, str]] = []

    class PlatformStub:
        def remember_session_scene(self, session_id: str, scene: str) -> None:
            remembered_scenes.append((session_id, scene))

        def remember_session_message_id(self, session_id: str, message_id: str) -> None:
            remembered_ids.append((session_id, message_id))

        def create_event(self, message_obj):
            return message_obj

        def commit_event(self, event) -> None:
            committed.append(event)

    client = QQOfficialBotClient(
        intents=botpy.Intents(public_messages=True),
        bot_log=False,
    )
    client.set_platform(cast(Any, PlatformStub()))

    await client.on_group_message_create(message)

    assert remembered_scenes == [("group-1", "group")]
    assert remembered_ids == [("group-1", "msg-1")]
    assert committed[0].type == MessageType.GROUP_MESSAGE
    assert committed[0].group_id == "group-1"
    assert committed[0].session_id == "group-1"


@pytest.mark.asyncio
async def test_ws_group_send_by_session_without_cached_msg_id_omits_msg_id():
    adapter = QQOfficialPlatformAdapter(
        {
            "id": "qq-official-test",
            "appid": "123",
            "secret": "secret",
            "enable_group_c2c": True,
            "enable_guild_direct_message": False,
        },
        {},
        asyncio.Queue(),
    )
    adapter.client.api = SimpleNamespace(
        post_group_message=AsyncMock(return_value={"id": "sent-1"}),
        post_message=AsyncMock(),
    )
    adapter._session_scene["group-1"] = "group"

    await adapter.send_by_session(
        MessageSession("qq_official", MessageType.GROUP_MESSAGE, "group-1"),
        MessageChain(chain=[Plain("proactive hello")]),
    )

    adapter.client.api.post_group_message.assert_awaited_once()
    kwargs = adapter.client.api.post_group_message.await_args.kwargs
    assert kwargs["group_openid"] == "group-1"
    assert kwargs["content"] == "proactive hello"
    assert "msg_id" not in kwargs
    assert "msg_seq" in kwargs
    assert adapter._session_last_message_id["group-1"] == "sent-1"


@pytest.mark.asyncio
async def test_ws_group_send_by_session_with_cached_msg_id_still_omits_msg_id():
    adapter = QQOfficialPlatformAdapter(
        {
            "id": "qq-official-test",
            "appid": "123",
            "secret": "secret",
            "enable_group_c2c": True,
            "enable_guild_direct_message": False,
        },
        {},
        asyncio.Queue(),
    )
    adapter.client.api = SimpleNamespace(
        post_group_message=AsyncMock(return_value={"id": "sent-2"}),
        post_message=AsyncMock(),
    )
    adapter._session_scene["group-1"] = "group"
    adapter._session_last_message_id["group-1"] = "stale-msg-id"

    await adapter.send_by_session(
        MessageSession("qq_official", MessageType.GROUP_MESSAGE, "group-1"),
        MessageChain(chain=[Plain("proactive with cache")]),
    )

    adapter.client.api.post_group_message.assert_awaited_once()
    kwargs = adapter.client.api.post_group_message.await_args.kwargs
    assert kwargs["group_openid"] == "group-1"
    assert kwargs["content"] == "proactive with cache"
    assert "msg_id" not in kwargs
    assert "msg_seq" in kwargs


@pytest.mark.asyncio
async def test_webhook_group_send_by_session_without_cached_msg_id_skips_send():
    adapter = QQOfficialWebhookPlatformAdapter(
        {
            "id": "qq-official-webhook-test",
            "appid": "123",
            "secret": "secret",
        },
        {},
        asyncio.Queue(),
    )
    adapter.client.api = SimpleNamespace(
        post_group_message=AsyncMock(return_value={"id": "sent-1"}),
        post_message=AsyncMock(),
    )
    adapter._session_scene["group-1"] = "group"

    await adapter.send_by_session(
        MessageSession("qq_official_webhook", MessageType.GROUP_MESSAGE, "group-1"),
        MessageChain(chain=[Plain("webhook proactive hello")]),
    )

    adapter.client.api.post_group_message.assert_not_awaited()
