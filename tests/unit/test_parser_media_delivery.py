from pathlib import Path
from types import SimpleNamespace

import pytest

from data.plugins.astrbot_plugin_parser.core.data import (
    ParseResult,
    Platform,
    VideoContent,
)
from data.plugins.astrbot_plugin_parser.core.sender import MessageSender


def test_parser_text_fallback_keeps_original_source_url() -> None:
    result = ParseResult(
        platform=Platform(name="bilibili", display_name="哔哩哔哩"),
        title="Example video",
        text="视频发送失败",
        url="https://www.bilibili.com/video/BV1Example",
    )

    segments = MessageSender._build_text_fallback(result)

    assert len(segments) == 1
    assert "视频发送失败" in segments[0].text
    assert "https://www.bilibili.com/video/BV1Example" in segments[0].text


def test_video_component_uses_callback_source_for_local_file(
    tmp_path: Path,
) -> None:
    from astrbot.core import astrbot_config, file_token_service
    from astrbot.core.message.components import Video

    path = tmp_path / "sample.mp4"
    path.write_bytes(b"video")
    previous = astrbot_config.get("callback_api_base")
    astrbot_config["callback_api_base"] = "http://host.docker.internal:6185"
    try:
        payload = __import__("asyncio").run(Video.fromFileSystem(path).to_dict())
    finally:
        astrbot_config["callback_api_base"] = previous
        file_token_service.staged_files.clear()

    assert payload["type"] == "video"
    assert payload["data"]["file"].startswith(
        "http://host.docker.internal:6185/api/file/"
    )


@pytest.mark.asyncio
async def test_parser_embeds_small_video_instead_of_sending_windows_path(
    tmp_path: Path,
) -> None:
    path = tmp_path / "small.mp4"
    path.write_bytes(b"video-source-bytes")
    sender = MessageSender(
        SimpleNamespace(audio_to_file=True, show_download_fail_tip=True),
        renderer=None,
    )
    result = ParseResult(
        platform=Platform(name="bilibili", display_name="哔哩哔哩"),
        url="https://www.bilibili.com/video/BV1Example",
    )
    plan = {
        "render_card": False,
        "force_merge": False,
        "light": [],
        "heavy": [VideoContent(path)],
    }

    segments = await sender._build_segments(result, plan)

    assert len(segments) == 1
    assert segments[0].file.startswith("base64://")
    assert "D:/" not in segments[0].file
