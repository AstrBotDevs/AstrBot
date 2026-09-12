import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import astrbot.api.message_components as Comp
from astrbot.api.platform import Group
from astrbot.core.pipeline.preprocess_stage import stage as preprocess_stage
from astrbot.core.platform.sources.mattermost.client import MattermostClient
from astrbot.core.platform.sources.mattermost.mattermost_adapter import (
    MattermostPlatformAdapter,
)
from astrbot.core.utils import media_utils
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
            "channel_display_name": "Town Square",
            "sender_name": "alice",
        },
    )

    assert result is not None
    assert result.group == Group(group_id="channel-1", group_name="Town Square")
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
    wav_path = str(tmp_path / "mattermost_voice.wav")

    file_infos = {
        "img": {"name": "image.png", "mime_type": "image/png"},
        "audio": {"name": "voice.ogg", "mime_type": "audio/ogg"},
        "video": {"name": "clip.mp4", "mime_type": "video/mp4"},
        "doc": {"name": "report.pdf", "mime_type": "application/pdf"},
    }

    client.get_file_info = AsyncMock(side_effect=lambda file_id: file_infos[file_id])
    client.download_file = AsyncMock(return_value=b"payload")

    class FakeMediaResolver:
        def __init__(self, media_ref: str, **kwargs) -> None:
            assert media_ref.endswith("mattermost_audio.ogg")
            assert kwargs["media_type"] == "audio"

        async def to_path(self, **kwargs) -> str:
            assert kwargs["target_format"] == "wav"
            return wav_path

    with (
        patch(
            "astrbot.core.platform.sources.mattermost.client.get_astrbot_temp_path",
            MagicMock(return_value=str(tmp_path)),
        ),
        patch(
            "astrbot.core.platform.sources.mattermost.client.MediaResolver",
            FakeMediaResolver,
        ),
    ):
        components, temp_paths = await client.parse_post_attachments(
            ["img", "audio", "video", "doc"]
        )

    assert len(components) == 4
    assert isinstance(components[0], Comp.Image)
    assert isinstance(components[1], Comp.Record)
    assert components[1].file == wav_path
    assert components[1].url == wav_path
    assert isinstance(components[2], Comp.Video)
    assert isinstance(components[3], Comp.File)
    assert len(temp_paths) == 4

    expected_names = ["image.png", "voice.ogg", "clip.mp4", "report.pdf"]
    for temp_path, expected_name in zip(temp_paths, expected_names):
        path = Path(temp_path)
        assert path.exists()
        assert path.name.endswith(Path(expected_name).suffix)


@pytest.mark.asyncio
@pytest.mark.parametrize("image_kind", ["png", "jpeg", "invalid"])
async def test_mattermost_attachments_follow_preprocessing_cleanup_rules(
    tmp_path, monkeypatch, image_kind
):
    import wave

    from PIL import Image as PILImage

    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    monkeypatch.setattr(
        preprocess_stage, "get_astrbot_temp_path", lambda: str(tmp_path)
    )
    image_path = tmp_path / f"image.{image_kind}"
    if image_kind == "invalid":
        image_path.write_bytes(b"not an image")
    else:
        PILImage.new("RGB", (2, 2), (255, 0, 0)).save(image_path)
    audio_path = tmp_path / "voice.wav"
    with wave.open(str(audio_path), "wb") as audio_file:
        audio_file.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        audio_file.writeframes(b"\x00\x00" * 80)
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"video")
    document_path = tmp_path / "report.pdf"
    document_path.write_bytes(b"document")
    downloaded_paths = [image_path, audio_path, video_path, document_path]
    image = Comp.Image.fromFileSystem(str(image_path))
    adapter = _build_adapter()
    adapter.client.parse_post_attachments = AsyncMock(
        return_value=(
            [
                image,
                Comp.Record(file=str(audio_path), url=str(audio_path)),
                Comp.Video.fromFileSystem(str(video_path)),
                Comp.File(name="report.pdf", file=str(document_path)),
            ],
            [str(path) for path in downloaded_paths],
        )
    )
    message = await adapter.convert_message(
        post={
            "id": "post-1",
            "channel_id": "channel-1",
            "user_id": "user-1",
            "message": "hello",
            "file_ids": ["img", "audio", "video", "doc"],
        },
        data={"channel_type": "D", "sender_name": "alice"},
    )
    event = adapter.create_event(message)
    assert event._temporary_local_files == []
    stage = preprocess_stage.PreProcessStage()
    stage.config = {}
    stage.platform_settings = {}
    stage.stt_settings = {"enable": False}

    await stage.process(event)
    event.cleanup_temporary_local_files()

    assert image_path.exists() == (image_kind != "png")
    assert not audio_path.exists()
    assert video_path.exists()
    assert document_path.exists()
    assert Path(await image.convert_to_file_path()).exists()
    if image_kind == "png":
        assert image.file != str(image_path)


@pytest.mark.asyncio
async def test_mattermost_get_group_returns_members_and_channel_admins():
    adapter = _build_adapter()
    adapter.client.get_channel = AsyncMock(
        return_value={"id": "channel-1", "display_name": "Town Square"},
    )
    adapter.client.get_channel_stats = AsyncMock(return_value={"member_count": 2})
    adapter.client.get_channel_members = AsyncMock(
        return_value=[
            {"user_id": "user-1", "roles": "channel_user channel_admin"},
            {"user_id": "user-2", "roles": "channel_user", "scheme_admin": True},
        ],
    )
    adapter.client.get_users_by_ids = AsyncMock(
        return_value=[
            {"id": "user-1", "username": "alice", "nickname": "Alice"},
            {"id": "user-2", "username": "bob"},
        ],
    )
    message = await adapter.convert_message(
        post={
            "id": "post-1",
            "channel_id": "channel-1",
            "user_id": "user-1",
            "message": "hello",
            "create_at": 1_700_000_000_000,
            "file_ids": [],
        },
        data={
            "channel_type": "O",
            "channel_display_name": "Cached Name",
            "sender_name": "alice",
        },
    )
    event = adapter.create_event(message)

    group = await event.get_group()

    assert group.group_name == "Town Square"
    assert group.group_owner is None
    assert group.member_count == 2
    assert [member.nickname for member in group.members] == ["Alice", "bob"]
    assert group.group_admins == ["user-1", "user-2"]


@pytest.mark.asyncio
async def test_mattermost_get_group_returns_cached_name_when_lookup_fails():
    adapter = _build_adapter()
    adapter.client.get_channel = AsyncMock(side_effect=RuntimeError("forbidden"))
    message = await adapter.convert_message(
        post={
            "id": "post-1",
            "channel_id": "channel-1",
            "user_id": "user-1",
            "message": "hello",
            "create_at": 1_700_000_000_000,
            "file_ids": [],
        },
        data={
            "channel_type": "O",
            "channel_display_name": "Cached Name",
            "sender_name": "alice",
        },
    )

    group = await adapter.create_event(message).get_group()

    assert group == Group(group_id="channel-1", group_name="Cached Name")
