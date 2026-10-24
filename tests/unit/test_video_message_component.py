import base64
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from astrbot.core.file_token_service import FileTokenService
from astrbot.core.message import components
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.utils import media_utils


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["base64", "data_uri", "path", "file_uri"])
async def test_video_callback_delivers_original_bytes(source, monkeypatch, tmp_path):
    video_bytes = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 8
    encoded = base64.b64encode(video_bytes).decode()
    local_path = tmp_path / "视频 clip.mp4"
    local_path.write_bytes(video_bytes)
    videos = {
        "base64": components.Video.fromBase64(encoded),
        "data_uri": components.Video(file=f"data:video/mp4;base64,{encoded}"),
        "path": components.Video(file=str(local_path)),
        "file_uri": components.Video.fromFileSystem(local_path),
    }
    token_service = FileTokenService()
    monkeypatch.setattr(components, "file_token_service", token_service)
    monkeypatch.setattr(
        components, "astrbot_config", {"callback_api_base": "https://callback.test/"}
    )
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    bot = AsyncMock()

    await AiocqhttpMessageEvent.send_message(
        bot=bot,
        message_chain=MessageChain([videos[source]]),
        is_group=True,
        session_id="123456",
    )

    payload = bot.send_group_msg.call_args.kwargs["message"]
    assert len(payload) == 1
    assert payload[0]["type"] == "video"
    callback_url = payload[0]["data"]["file"]
    assert callback_url.startswith("https://callback.test/api/file/")
    token = callback_url.rsplit("/", 1)[1]
    registered_path = await token_service.handle_file(token)
    assert Path(registered_path).read_bytes() == video_bytes


@pytest.mark.asyncio
@pytest.mark.parametrize("callback", ["", "https://callback.test/"])
async def test_video_http_url_is_preserved(callback, monkeypatch):
    monkeypatch.setattr(components, "astrbot_config", {"callback_api_base": callback})
    video = components.Video.fromURL("https://media.test/clip.mp4")

    assert await video.to_dict() == {
        "type": "video",
        "data": {"file": "https://media.test/clip.mp4"},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["base64", "file_uri"])
async def test_video_without_callback_preserves_reference(
    source, monkeypatch, tmp_path
):
    monkeypatch.setattr(components, "astrbot_config", {"callback_api_base": ""})
    video = (
        components.Video.fromBase64("dmlkZW8=")
        if source == "base64"
        else components.Video.fromFileSystem(tmp_path / "视频 clip.mp4")
    )

    assert await video.to_dict() == {"type": "video", "data": {"file": video.file}}


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["path", "file_uri", "path_with_fallback"])
async def test_video_callback_preserves_missing_file_error(
    source, monkeypatch, tmp_path
):
    monkeypatch.setattr(
        components, "astrbot_config", {"callback_api_base": "https://callback.test"}
    )
    monkeypatch.setattr(components, "file_token_service", FileTokenService())
    missing = tmp_path / "missing.mp4"
    fallback = tmp_path / "fallback.mp4"
    fallback.write_bytes(b"another video")
    video = components.Video(
        file=missing.as_uri() if source == "file_uri" else str(missing),
        path=str(fallback) if source == "path_with_fallback" else "",
    )

    with pytest.raises(FileNotFoundError):
        await video.to_dict()
