"""Test Discord payloads and channel lookup with real SDK value objects."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.core.message.components import At, Image, Plain, Reply
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.discord import discord_platform_event as module


@pytest.fixture
def discord_event():
    """Construct a real event with fixture-owned client transport methods."""
    message = AstrBotMessage()
    message.type = MessageType.GROUP_MESSAGE
    message.message = []
    message.message_str = ""
    message.sender = MessageMember(user_id="user-1", nickname="User")
    message.raw_message = None
    client = SimpleNamespace(get_channel=Mock(), fetch_channel=AsyncMock())
    return module.DiscordPlatformEvent(
        "",
        message,
        PlatformMetadata(name="discord", description="Test", id="discord-test"),
        "42",
        client,
    )


@pytest.mark.asyncio
async def test_remote_image_is_embedded_without_download(monkeypatch, discord_event):
    resolver = Mock(side_effect=AssertionError("Remote images must use embeds"))
    monkeypatch.setattr(module, "MediaResolver", resolver)
    event = discord_event
    chain = MessageChain(
        [
            Plain("Hi "),
            At(qq="42"),
            Plain("!"),
            Reply(id="original-message"),
            Image.fromURL("https://example.test/image.gif"),
        ]
    )

    content, files, view, embeds, reference = await event._parse_to_discord(chain)

    assert content == "Hi <@42>!"
    assert files == []
    assert view is None
    assert reference == "original-message"
    assert len(embeds) == 1
    assert embeds[0].image.url == "https://example.test/image.gif"
    resolver.assert_not_called()
    assert len(chain.chain) == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("cached", [True, False])
async def test_channel_cache_avoids_unnecessary_fetch(cached, discord_event):
    channel = object()
    event = discord_event
    event.session_id = "42"
    event.client = SimpleNamespace(
        get_channel=Mock(return_value=channel if cached else None),
        fetch_channel=AsyncMock(return_value=channel),
    )

    assert await event._get_channel() is channel

    event.client.get_channel.assert_called_once_with(42)
    if cached:
        event.client.fetch_channel.assert_not_awaited()
    else:
        event.client.fetch_channel.assert_awaited_once_with(42)


@pytest.mark.asyncio
async def test_invalid_channel_id_never_reaches_transport(discord_event):
    event = discord_event
    event.session_id = "invalid"
    event.client = SimpleNamespace(get_channel=Mock(), fetch_channel=AsyncMock())

    assert await event._get_channel() is None

    event.client.get_channel.assert_not_called()
    event.client.fetch_channel.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_propagates_cancellation_without_retry(discord_event):
    event = discord_event
    send = AsyncMock(side_effect=asyncio.CancelledError)
    event.interaction_followup_webhook = SimpleNamespace(send=send)

    with pytest.raises(asyncio.CancelledError):
        await event.send(MessageChain([Plain("cancel me")]))

    send.assert_awaited_once_with(content="cancel me")
