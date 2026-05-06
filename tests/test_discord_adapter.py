from unittest.mock import MagicMock

import pytest

from astrbot.api.message_components import File, Image, Record
from tests.fixtures.helpers import (
    create_mock_discord_attachment,
    create_mock_discord_user,
    make_platform_config,
)

pytest_plugins = ("tests.fixtures.mocks.discord",)


def _make_adapter(event_queue, platform_settings):
    from astrbot.core.platform.sources.discord.discord_platform_adapter import (
        DiscordPlatformAdapter,
    )
    from tests.fixtures.mocks.discord import MockDiscordBuilder

    adapter = DiscordPlatformAdapter(
        make_platform_config("discord"),
        platform_settings,
        event_queue,
    )
    adapter.client = MockDiscordBuilder.create_client()
    adapter.bot_self_id = str(adapter.client.user.id)
    return adapter


def _make_message(attachment):
    message = MagicMock()
    message.content = ""
    message.attachments = [attachment]
    message.channel = MagicMock()
    message.channel.id = 111222333
    message.channel.guild = MagicMock()
    message.author = create_mock_discord_user()
    message.guild = None
    message.role_mentions = []
    message.id = 555666777
    return message


@pytest.mark.parametrize(
    ("attachment", "expected_type"),
    [
        (
            create_mock_discord_attachment(
                filename="voice-message.ogg",
                url="https://cdn.discordapp.com/voice-message.ogg",
                content_type="audio/ogg",
            ),
            Record,
        ),
        (
            create_mock_discord_attachment(
                filename="voice-message.ogg",
                url="https://cdn.discordapp.com/voice-message.ogg",
                content_type=None,
            ),
            Record,
        ),
        (
            create_mock_discord_attachment(
                filename="image.png",
                url="https://cdn.discordapp.com/image.png",
                content_type="image/png",
            ),
            Image,
        ),
        (
            create_mock_discord_attachment(
                filename="document.txt",
                url="https://cdn.discordapp.com/document.txt",
                content_type="text/plain",
            ),
            File,
        ),
    ],
)
def test_discord_attachment_media_mapping(
    attachment,
    expected_type,
    event_queue,
    platform_settings,
    mock_discord_modules,
):
    adapter = _make_adapter(event_queue, platform_settings)

    abm = adapter._convert_message_to_abm({"message": _make_message(attachment)})

    assert len(abm.message) == 1
    assert isinstance(abm.message[0], expected_type)


def test_discord_audio_attachment_preserves_url(
    event_queue,
    platform_settings,
    mock_discord_modules,
):
    adapter = _make_adapter(event_queue, platform_settings)
    attachment = create_mock_discord_attachment(
        filename="voice-message.ogg",
        url="https://cdn.discordapp.com/voice-message.ogg",
        content_type="audio/ogg",
    )

    abm = adapter._convert_message_to_abm({"message": _make_message(attachment)})

    assert isinstance(abm.message[0], Record)
    assert abm.message[0].file == attachment.url
    assert abm.message[0].url == attachment.url
