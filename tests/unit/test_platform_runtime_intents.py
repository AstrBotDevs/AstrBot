"""Exercise uncached Discord replies and Satori metadata/routing boundaries."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import discord
import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain, Reply
from astrbot.api.platform import (
    AstrBotMessage,
    Group,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.sources.discord import discord_platform_event
from astrbot.core.platform.sources.discord.client import DiscordBotClient
from astrbot.core.platform.sources.satori.satori_adapter import SatoriPlatformAdapter
from astrbot.core.platform.sources.satori.satori_event import SatoriPlatformEvent


def _incoming(raw_message: object = None) -> AstrBotMessage:
    message = AstrBotMessage()
    message.type = MessageType.GROUP_MESSAGE
    message.message = []
    message.message_str = "input"
    message.message_id = "100"
    message.self_id = "bot"
    message.session_id = "42"
    message.sender = MessageMember("sender", "Sender")
    message.raw_message = raw_message
    return message


@pytest.fixture
def completed(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    callback = AsyncMock()
    monkeypatch.setattr(AstrMessageEvent, "send", callback)
    return callback


@pytest.fixture
def discord_case(monkeypatch: pytest.MonkeyPatch, completed: AsyncMock):
    channel = Mock(spec=discord.TextChannel, id=42, send=AsyncMock())
    client = object.__new__(DiscordBotClient)
    cache_lookup = Mock(return_value=None)
    client._connection = SimpleNamespace(_get_message=cache_lookup)
    client.get_channel = Mock(return_value=channel)
    client.fetch_channel = AsyncMock(return_value=channel)
    event = discord_platform_event.DiscordPlatformEvent(
        "input",
        _incoming(),
        PlatformMetadata("discord", "Discord", "discord-test"),
        "42",
        client,
    )
    logger = Mock()
    monkeypatch.setattr(discord_platform_event, "logger", logger)
    return SimpleNamespace(
        event=event,
        client=client,
        channel=channel,
        cache_lookup=cache_lookup,
        completed=completed,
        logger=logger,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "channel_type", [discord.TextChannel, discord.DMChannel, discord.Thread]
)
async def test_discord_uncached_reply_keeps_message_and_channel_identity(
    discord_case, channel_type
) -> None:
    channel = Mock(spec=channel_type, id=42, send=AsyncMock())
    discord_case.client.get_channel.return_value = channel
    chain = MessageChain([Reply(id="123"), Plain("reply")])

    await discord_case.event.send(chain)

    channel.send.assert_awaited_once()
    kwargs = channel.send.call_args.kwargs
    reference = kwargs["reference"]
    assert isinstance(reference, discord.MessageReference)
    assert reference.to_message_reference_dict() == {
        "message_id": 123,
        "channel_id": 42,
        "type": discord.MessageReferenceType.default.value,
        "fail_if_not_exists": True,
    }
    assert kwargs["content"] == "reply"
    discord_case.cache_lookup.assert_not_called()
    discord_case.client.fetch_channel.assert_not_awaited()
    discord_case.completed.assert_awaited_once_with(chain)


@pytest.mark.asyncio
async def test_discord_message_without_reply_omits_reference(discord_case) -> None:
    chain = MessageChain([Plain("ordinary message")])

    await discord_case.event.send(chain)

    discord_case.channel.send.assert_awaited_once_with(content="ordinary message")
    discord_case.cache_lookup.assert_not_called()
    discord_case.completed.assert_awaited_once_with(chain)


@pytest.mark.asyncio
async def test_discord_followup_omits_channel_reference_and_lookup(
    discord_case,
) -> None:
    followup = SimpleNamespace(send=AsyncMock())
    discord_case.event.interaction_followup_webhook = followup
    chain = MessageChain([Reply(id="not-a-channel-message-id"), Plain("followup")])

    await discord_case.event.send(chain)

    followup.send.assert_awaited_once_with(content="followup")
    discord_case.client.get_channel.assert_not_called()
    discord_case.client.fetch_channel.assert_not_awaited()
    discord_case.cache_lookup.assert_not_called()
    discord_case.completed.assert_awaited_once_with(chain)


@pytest.mark.asyncio
async def test_discord_reply_without_content_does_not_send(discord_case) -> None:
    await discord_case.event.send(MessageChain([Reply(id="123")]))

    discord_case.channel.send.assert_not_awaited()
    discord_case.client.get_channel.assert_not_called()
    discord_case.cache_lookup.assert_not_called()
    discord_case.completed.assert_not_awaited()


@pytest.mark.asyncio
async def test_discord_invalid_reply_id_uses_existing_send_error_boundary(
    discord_case,
) -> None:
    chain = MessageChain([Reply(id="invalid"), Plain("reply")])

    await discord_case.event.send(chain)

    discord_case.channel.send.assert_not_awaited()
    discord_case.logger.error.assert_called_once()
    discord_case.completed.assert_awaited_once_with(chain)


@pytest.mark.asyncio
async def test_discord_parse_error_stops_before_send_and_completion(
    discord_case,
) -> None:
    discord_case.event._parse_to_discord = AsyncMock(
        side_effect=ValueError("bad component")
    )

    await discord_case.event.send(MessageChain([Plain("input")]))

    discord_case.channel.send.assert_not_awaited()
    discord_case.client.get_channel.assert_not_called()
    discord_case.logger.error.assert_called_once()
    discord_case.completed.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [TimeoutError, RuntimeError])
async def test_discord_send_error_does_not_replay_reply(discord_case, failure) -> None:
    discord_case.channel.send.side_effect = failure("delivery uncertain")
    chain = MessageChain([Reply(id="123"), Plain("reply")])

    await discord_case.event.send(chain)

    discord_case.channel.send.assert_awaited_once()
    discord_case.logger.error.assert_called_once()
    discord_case.completed.assert_awaited_once_with(chain)


@pytest.mark.asyncio
async def test_discord_reply_cancellation_propagates_without_completion(
    discord_case,
) -> None:
    discord_case.channel.send.side_effect = asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await discord_case.event.send(MessageChain([Reply(id="123"), Plain("reply")]))

    discord_case.channel.send.assert_awaited_once()
    discord_case.completed.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("unavailable", [None, discord.CategoryChannel])
async def test_discord_unavailable_channel_stops_before_completion(
    discord_case, unavailable
) -> None:
    channel = None if unavailable is None else Mock(spec=unavailable, id=42)
    discord_case.client.get_channel.return_value = channel
    discord_case.client.fetch_channel.return_value = channel

    await discord_case.event.send(MessageChain([Reply(id="123"), Plain("reply")]))

    discord_case.channel.send.assert_not_awaited()
    discord_case.completed.assert_not_awaited()


@pytest.fixture
def satori_adapter():
    response = SimpleNamespace(status=200, json=AsyncMock(return_value={"id": "sent"}))
    context = AsyncMock()
    context.__aenter__.return_value = response
    adapter = object.__new__(SatoriPlatformAdapter)
    adapter.token = "test-token"
    adapter.api_base_url = "http://localhost/v1"
    adapter.session = SimpleNamespace(request=Mock(return_value=context))
    adapter.logins = [
        {"platform": "slack", "user": {"id": "slack-bot"}},
        {"platform": "qq", "user": {"id": "qq-bot"}},
    ]
    return adapter


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw", "platform", "user_id"),
    [
        ({"login": {"platform": "qq", "user": {"id": "qq-bot"}}}, "qq", "qq-bot"),
        ({}, "slack", "slack-bot"),
        (None, "slack", "slack-bot"),
    ],
)
async def test_satori_metadata_survives_instance_send_with_correct_account_headers(
    satori_adapter, completed: AsyncMock, raw: object, platform: str, user_id: str
) -> None:
    metadata = PlatformMetadata("satori", "Satori", "satori-test")
    event = SatoriPlatformEvent("input", _incoming(raw), metadata, "42", satori_adapter)
    chain = MessageChain([Plain("reply")])

    await event.send(chain)

    request = satori_adapter.session.request
    request.assert_called_once()
    assert request.call_args.args == ("POST", "http://localhost/v1/message.create")
    assert request.call_args.kwargs["json"] == {"channel_id": "42", "content": "reply"}
    assert request.call_args.kwargs["headers"] == {
        "Content-Type": "application/json",
        "Authorization": "Bearer test-token",
        "satori-platform": platform,
        "satori-user-id": user_id,
    }
    assert event.platform is metadata
    assert event.platform_meta is metadata
    assert event.get_platform_name() == "satori"
    assert event.get_platform_id() == "satori-test"
    completed.assert_awaited_once_with(chain)


def test_satori_missing_login_preserves_metadata(satori_adapter) -> None:
    satori_adapter.logins = []
    metadata = PlatformMetadata("satori", "Satori", "satori-test")

    event = SatoriPlatformEvent("input", _incoming(), metadata, "42", satori_adapter)

    assert event.platform is metadata
    assert event.satori_platform is None
    assert event.user_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("supported", [False, True])
async def test_satori_group_uses_event_login_features_and_routing(
    satori_adapter, supported: bool
) -> None:
    login = satori_adapter.logins[1]
    login["features"] = ["guild.get", "guild.member.list"] if supported else []
    message = _incoming({"login": login})
    message.group = Group("guild-1", group_name="Inbound")
    metadata = PlatformMetadata("satori", "Satori", "satori-test")
    satori_adapter.send_http_request = AsyncMock(
        side_effect=[{"name": "Fetched"}, {"data": [{"user": {"id": "member"}}]}]
    )
    event = SatoriPlatformEvent("input", message, metadata, "42", satori_adapter)

    group = await event.get_group()

    assert group is not None
    if supported:
        assert satori_adapter.send_http_request.await_args_list == [
            call("POST", "/guild.get", {"guild_id": "guild-1"}, "qq", "qq-bot"),
            call("POST", "/guild.member.list", {"guild_id": "guild-1"}, "qq", "qq-bot"),
        ]
        assert group.group_name == "Fetched"
        assert group.members == [MessageMember("member")]
    else:
        satori_adapter.send_http_request.assert_not_awaited()
        assert group.group_name == "Inbound"
    assert event.platform is metadata
    assert message.group.group_name == "Inbound"
