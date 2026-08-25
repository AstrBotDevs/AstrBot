import base64
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.api.message_components import (
    ActionRow,
    Button,
    ButtonInteraction,
    ButtonStyle,
    CallbackAction,
    Image,
    Plain,
    Record,
    UrlAction,
)
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.button_interaction import (
    decode_button_callback,
    encode_button_callback,
)
from astrbot.core.platform.sources.discord import (
    client as discord_client,
)
from astrbot.core.platform.sources.discord import (
    discord_platform_adapter,
    discord_platform_event,
)
from astrbot.core.platform.sources.discord.client import DiscordBotClient
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


@pytest.mark.asyncio
async def test_discord_renders_common_action_rows():
    event = DiscordPlatformEvent.__new__(DiscordPlatformEvent)

    content, files, view, embeds, reference_message_id = await event._parse_to_discord(
        MessageChain(
            chain=[
                Plain("Choose an action"),
                ActionRow(
                    buttons=[
                        Button(
                            id="approve",
                            label="Approve",
                            action=CallbackAction(data={"order_id": 7}),
                            style=ButtonStyle.SUCCESS,
                        ),
                        Button(
                            id="docs",
                            label="Documentation",
                            action=UrlAction(url="https://example.com/docs"),
                        ),
                    ]
                ),
            ]
        )
    )

    assert content == "Choose an action"
    assert files == []
    assert embeds == []
    assert reference_message_id is None
    assert view is not None
    assert len(view.children) == 2
    action_id, data = decode_button_callback(view.children[0].custom_id)
    assert action_id == "approve"
    assert data == {"order_id": 7}
    assert view.children[0].style == discord_platform_event.discord.ButtonStyle.success
    assert view.children[1].url == "https://example.com/docs"
    assert view.children[1].style == discord_platform_event.discord.ButtonStyle.link


@pytest.mark.asyncio
async def test_discord_converts_component_interaction_to_common_event():
    adapter = DiscordPlatformAdapter.__new__(DiscordPlatformAdapter)
    adapter.bot_self_id = "99"
    interaction = SimpleNamespace(
        id=456,
        data={"custom_id": encode_button_callback("approve", {"order_id": 7})},
        guild_id=321,
        channel_id=123,
        user=SimpleNamespace(id=42, display_name="tester"),
        message=SimpleNamespace(id=789),
    )

    message = await adapter.convert_message(
        {"type": "interaction", "interaction": interaction}
    )

    assert message.message_str == "approve"
    assert message.session_id == "123"
    assert message.message_id == "456"
    assert len(message.message) == 1
    assert isinstance(message.message[0], ButtonInteraction)
    assert message.message[0].action_id == "approve"
    assert message.message[0].data == {"order_id": 7}
    assert message.message[0].interaction_id == "456"
    assert message.message[0].source_message_id == "789"


@pytest.mark.asyncio
async def test_discord_client_acknowledges_component_before_dispatch(monkeypatch):
    process_application_commands = AsyncMock()
    monkeypatch.setattr(
        discord_client.discord.Bot,
        "on_interaction",
        process_application_commands,
    )
    client = DiscordBotClient.__new__(DiscordBotClient)
    client._connection = SimpleNamespace(user=SimpleNamespace(id=99))
    client.on_message_received = AsyncMock()
    response = SimpleNamespace(is_done=lambda: False, defer=AsyncMock())
    interaction = SimpleNamespace(
        id=456,
        type=discord_client.discord.InteractionType.component,
        data={
            "component_type": discord_client.discord.ComponentType.button.value,
            "custom_id": encode_button_callback("approve"),
        },
        user=SimpleNamespace(id=42, display_name="tester"),
        response=response,
        channel_id=123,
        guild_id=321,
    )

    await client.on_interaction(interaction)

    process_application_commands.assert_not_awaited()
    response.defer.assert_awaited_once_with()
    client.on_message_received.assert_awaited_once()
