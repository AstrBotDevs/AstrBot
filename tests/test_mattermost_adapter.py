import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import astrbot.api.message_components as Comp
from astrbot.core.platform.sources.mattermost.client import MattermostClient
from astrbot.core.platform.sources.mattermost.mattermost_adapter import (
    MattermostPlatformAdapter,
)
from tests.fixtures.helpers import make_platform_config


def _build_adapter() -> MattermostPlatformAdapter:
    adapter = MattermostPlatformAdapter(
        make_platform_config(
            "mattermost",
            id="test_mattermost",
            mattermost_url="https://chat.example.com",
            mattermost_bot_token="test_token",
            mattermost_reconnect_delay=5.0,
        ),
        {},
        asyncio.Queue(),
    )
    adapter.bot_self_id = "bot-id"
    adapter.bot_username = "bot"
    adapter._mention_pattern = adapter._build_mention_pattern(adapter.bot_username)
    return adapter


@pytest.mark.asyncio
async def test_mattermost_convert_message_strips_leading_self_mention():
    adapter = _build_adapter()

    result = await adapter.convert_message(
        post={
            "id": "post-1",
            "channel_id": "channel-1",
            "user_id": "user-1",
            "message": "@bot /help now",
            "create_at": 1_700_000_000_000,
            "file_ids": [],
        },
        data={
            "channel_type": "O",
            "sender_name": "alice",
        },
    )

    assert result is not None
    assert result.message_str == "/help now"
    assert isinstance(result.message[0], Comp.At)
    assert result.message[0].qq == "bot-id"
    assert any(
        isinstance(component, Comp.Plain) and component.text.strip() == "/help now"
        for component in result.message
    )


@pytest.mark.asyncio
async def test_mattermost_parse_post_attachments_maps_media_types(tmp_path):
    client = MattermostClient("https://chat.example.com", "test_token")

    file_infos = {
        "img": {"name": "image.png", "mime_type": "image/png"},
        "audio": {"name": "voice.ogg", "mime_type": "audio/ogg"},
        "video": {"name": "clip.mp4", "mime_type": "video/mp4"},
        "doc": {"name": "report.pdf", "mime_type": "application/pdf"},
    }

    client.get_file_info = AsyncMock(side_effect=lambda file_id: file_infos[file_id])
    client.download_file = AsyncMock(return_value=b"payload")

    with patch(
        "astrbot.core.platform.sources.mattermost.client.get_astrbot_temp_path",
        MagicMock(return_value=str(tmp_path)),
    ):
        components, temp_paths = await client.parse_post_attachments(
            ["img", "audio", "video", "doc"]
        )

    assert len(components) == 4
    assert isinstance(components[0], Comp.Image)
    assert isinstance(components[1], Comp.Record)
    assert isinstance(components[2], Comp.Video)
    assert isinstance(components[3], Comp.File)
    assert len(temp_paths) == 4

    expected_names = ["image.png", "voice.ogg", "clip.mp4", "report.pdf"]
    for temp_path, expected_name in zip(temp_paths, expected_names):
        path = Path(temp_path)
        assert path.exists()
        assert path.name.endswith(Path(expected_name).suffix)
