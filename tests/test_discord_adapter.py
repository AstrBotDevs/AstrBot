import base64
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.api.message_components import Image, Record
from astrbot.api.platform import Group, MessageType
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.sources.discord import (
    discord_platform_adapter,
    discord_platform_event,
)
from astrbot.core.platform.sources.discord.discord_platform_adapter import (
    DiscordPlatformAdapter,
)
from astrbot.core.platform.sources.discord.discord_platform_event import (
    DiscordPlatformEvent,
)

_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)
_WAV_BYTES = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 16
_WAV_PATH = "/tmp/discord_voice.wav"


@pytest.mark.asyncio
async def test_discord_group_message_includes_guild_and_channel_name():
    adapter = DiscordPlatformAdapter.__new__(DiscordPlatformAdapter)
    adapter.bot_self_id = "1"
    adapter.client = SimpleNamespace(user=SimpleNamespace(id=1))
    guild = SimpleNamespace(name="AstrBot", get_member=lambda member_id: None)
    message = SimpleNamespace(
        id=42,
        content="hello",
        channel=SimpleNamespace(id=123, name="general", guild=guild),
        author=SimpleNamespace(id=2, display_name="tester"),
        attachments=[],
        guild=guild,
        role_mentions=[],
    )

    abm = await adapter.convert_message({"message": message})

    assert abm.group is not None
    assert abm.group.group_id == "123"
    assert abm.group.group_name == "AstrBot-general"


@pytest.mark.asyncio
async def test_discord_private_message_does_not_get_group_name():
    adapter = DiscordPlatformAdapter.__new__(DiscordPlatformAdapter)
    adapter.bot_self_id = "1"
    adapter.client = SimpleNamespace(user=SimpleNamespace(id=1))
    message = SimpleNamespace(
        id=42,
        content="hello",
        channel=SimpleNamespace(id=123, name="direct-message", guild=None),
        author=SimpleNamespace(id=2, display_name="tester"),
        attachments=[],
        guild=None,
        role_mentions=[],
    )

    abm = await adapter.convert_message({"message": message})

    assert abm.type == MessageType.FRIEND_MESSAGE
    assert abm.group is not None
    assert abm.group.group_name is None


def test_discord_group_name_falls_back_when_one_name_is_missing():
    assert (
        DiscordPlatformAdapter._get_group_name(
            SimpleNamespace(name="general", guild=SimpleNamespace(name=None))
        )
        == "general"
    )
    assert (
        DiscordPlatformAdapter._get_group_name(
            SimpleNamespace(name=None, guild=SimpleNamespace(name="AstrBot"))
        )
        == "AstrBot"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("guild_name", "channel_name", "expected_name"),
    [(None, "general", "general"), ("AstrBot", None, "AstrBot")],
)
async def test_discord_get_group_name_falls_back_when_one_name_is_missing(
    guild_name, channel_name, expected_name
):
    guild = SimpleNamespace(
        name=guild_name,
        icon=None,
        owner_id=None,
        member_count=None,
        members=[],
        chunked=False,
    )
    channel = SimpleNamespace(id=123, name=channel_name, guild=guild)
    event = DiscordPlatformEvent.__new__(DiscordPlatformEvent)
    event.message_obj = SimpleNamespace(
        type=MessageType.GROUP_MESSAGE,
        group=Group(group_id="123", group_name="cached"),
        group_id="123",
    )
    event.client = SimpleNamespace(
        get_channel=lambda channel_id: channel,
        intents=SimpleNamespace(members=False),
    )

    group = await event.get_group()

    assert group is not None
    assert group.group_name == expected_name


@pytest.mark.asyncio
async def test_discord_get_group_fetches_uncached_guild_name():
    channel = SimpleNamespace(
        id=123,
        name="general",
        guild=SimpleNamespace(id=456),
    )
    guild = SimpleNamespace(
        id=456,
        name="AstrBot",
        icon=None,
        owner_id=None,
        member_count=None,
        members=[],
        chunked=False,
    )
    client = SimpleNamespace(
        get_channel=lambda channel_id: None,
        fetch_channel=AsyncMock(return_value=channel),
        get_guild=lambda guild_id: None,
        fetch_guild=AsyncMock(return_value=guild),
        intents=SimpleNamespace(members=False),
    )
    event = DiscordPlatformEvent.__new__(DiscordPlatformEvent)
    event.message_obj = SimpleNamespace(
        type=MessageType.GROUP_MESSAGE,
        group=Group(group_id="123"),
        group_id="123",
    )
    event.client = client

    group = await event.get_group()

    assert group is not None
    assert group.group_name == "AstrBot-general"
    client.fetch_channel.assert_awaited_once_with(123)
    client.fetch_guild.assert_awaited_once_with(456)


@pytest.mark.asyncio
async def test_discord_get_group_enriches_guild_metadata_from_complete_cache():
    members = [
        SimpleNamespace(
            id=1,
            display_name="owner",
            guild_permissions=SimpleNamespace(administrator=True),
        ),
        SimpleNamespace(
            id=2,
            display_name="admin",
            guild_permissions=SimpleNamespace(administrator=True),
        ),
        SimpleNamespace(
            id=3,
            display_name="member",
            guild_permissions=SimpleNamespace(administrator=False),
        ),
    ]
    guild = SimpleNamespace(
        name="AstrBot",
        icon=SimpleNamespace(url="https://cdn.discordapp.com/guild.png"),
        owner_id=1,
        member_count=3,
        members=members,
        chunked=True,
    )
    channel = SimpleNamespace(
        id=123,
        name="general",
        guild=guild,
        permissions_for=lambda member: SimpleNamespace(view_channel=True),
    )
    client = SimpleNamespace(
        get_channel=lambda channel_id: channel,
        fetch_channel=AsyncMock(),
        intents=SimpleNamespace(members=True),
    )
    event = DiscordPlatformEvent.__new__(DiscordPlatformEvent)
    event.message_obj = SimpleNamespace(
        type=MessageType.GROUP_MESSAGE,
        group=Group(group_id="123", group_name="general"),
        group_id="123",
    )
    event.client = client

    group = await event.get_group()

    assert group is not None
    assert group.group_id == "123"
    assert group.group_name == "AstrBot-general"
    assert group.group_avatar == "https://cdn.discordapp.com/guild.png"
    assert group.group_owner == "1"
    assert group.member_count == 3
    assert group.group_admins == ["2"]
    assert group.members is not None
    assert [member.user_id for member in group.members] == ["1", "2", "3"]
    client.fetch_channel.assert_not_awaited()


@pytest.mark.asyncio
async def test_discord_get_group_returns_none_for_private_message():
    event = DiscordPlatformEvent.__new__(DiscordPlatformEvent)
    event.message_obj = SimpleNamespace(
        type=MessageType.FRIEND_MESSAGE,
        group=None,
        group_id="123",
    )
    event.client = SimpleNamespace()

    assert await event.get_group() is None


@pytest.mark.asyncio
async def test_discord_get_group_keeps_basic_metadata_when_channel_fetch_fails():
    client = SimpleNamespace(
        get_channel=lambda channel_id: None,
        fetch_channel=AsyncMock(side_effect=RuntimeError("channel unavailable")),
    )
    event = DiscordPlatformEvent.__new__(DiscordPlatformEvent)
    event.message_obj = SimpleNamespace(
        type=MessageType.GROUP_MESSAGE,
        group=Group(group_id="123", group_name="general"),
        group_id="123",
    )
    event.client = client

    group = await event.get_group()

    assert group == Group(group_id="123", group_name="general")


@pytest.mark.asyncio
async def test_discord_audio_attachment_resolves_to_wav_record(monkeypatch):
    class FakeMediaResolver:
        def __init__(self, media_ref: str, **kwargs) -> None:
            assert media_ref == "https://cdn.example/voice.ogg"
            assert kwargs["media_type"] == "audio"

        async def to_path(self, **kwargs) -> str:
            assert kwargs["target_format"] == "wav"
            return _WAV_PATH

    monkeypatch.setattr(
        discord_platform_adapter,
        "MediaResolver",
        FakeMediaResolver,
    )

    adapter = DiscordPlatformAdapter.__new__(DiscordPlatformAdapter)
    adapter.bot_self_id = "1"
    adapter.client = SimpleNamespace(user=SimpleNamespace(id=1))

    message = SimpleNamespace(
        id=42,
        content="",
        channel=SimpleNamespace(id=123, guild=None),
        author=SimpleNamespace(id=2, display_name="tester"),
        attachments=[
            SimpleNamespace(
                content_type="audio/ogg",
                filename="voice.ogg",
                url="https://cdn.example/voice.ogg",
            )
        ],
        guild=None,
        role_mentions=[],
    )

    abm = await adapter.convert_message({"message": message})

    assert len(abm.message) == 1
    assert isinstance(abm.message[0], Record)
    assert abm.message[0].file == _WAV_PATH
    assert abm.message[0].url == _WAV_PATH
    assert abm.message[0].path == _WAV_PATH


@pytest.mark.asyncio
async def test_discord_send_image_resolves_data_uri_with_media_resolver(monkeypatch):
    captured = {}

    class FakeDiscordFile:
        def __init__(self, fp: BytesIO, filename: str) -> None:
            captured["bytes"] = fp.read()
            captured["filename"] = filename

    monkeypatch.setattr(discord_platform_event.discord, "File", FakeDiscordFile)

    event = DiscordPlatformEvent.__new__(DiscordPlatformEvent)
    image_base64 = base64.b64encode(_PNG_BYTES).decode("ascii")

    content, files, view, embeds, reference_message_id = await event._parse_to_discord(
        MessageChain(
            chain=[
                Image(file=f"data:image/png;base64,{image_base64}"),
            ]
        )
    )

    assert content == ""
    assert len(files) == 1
    assert captured["bytes"] == _PNG_BYTES
    assert captured["filename"] == "image.png"
    assert view is None
    assert embeds == []
    assert reference_message_id is None


@pytest.mark.asyncio
async def test_discord_send_record_resolves_audio_with_media_resolver(monkeypatch):
    captured = {}

    class FakeDiscordFile:
        def __init__(self, fp: BytesIO, filename: str) -> None:
            captured["bytes"] = fp.read()
            captured["filename"] = filename

    monkeypatch.setattr(discord_platform_event.discord, "File", FakeDiscordFile)

    event = DiscordPlatformEvent.__new__(DiscordPlatformEvent)
    audio_base64 = base64.b64encode(_WAV_BYTES).decode("ascii")

    content, files, view, embeds, reference_message_id = await event._parse_to_discord(
        MessageChain(
            chain=[
                Record.fromBase64(audio_base64),
            ]
        )
    )

    assert content == ""
    assert len(files) == 1
    assert captured["bytes"] == _WAV_BYTES
    assert captured["filename"] == "audio.wav"
    assert view is None
    assert embeds == []
    assert reference_message_id is None
