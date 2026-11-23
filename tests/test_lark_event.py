"""Check Lark rich-message conversion against real message components."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image as PILImage

from astrbot.core.message.components import At, File, Image, Plain, Record, Video
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.sources.lark import lark_event as module


@pytest.mark.asyncio
async def test_text_and_mentions_preserve_order_without_transport():
    client = Mock()
    chain = MessageChain([Plain("before "), At(qq="user-1"), Plain(" after")])

    converted = await module.LarkMessageEvent._convert_to_lark(chain, client)

    assert converted == [
        [
            {"tag": "md", "text": "before "},
            {"tag": "at", "user_id": "user-1", "style": []},
            {"tag": "md", "text": " after"},
        ]
    ]
    assert client.mock_calls == []
    assert chain.chain[0].text == "before "


@pytest.mark.asyncio
async def test_local_image_upload_preserves_bytes_and_surrounding_text(
    tmp_path, monkeypatch
):
    image_path = tmp_path / "image.gif"
    PILImage.new("P", (2, 2), 1).save(image_path, format="GIF")
    image_bytes = image_path.read_bytes()
    upload = AsyncMock(
        return_value=SimpleNamespace(
            success=lambda: True, data=SimpleNamespace(image_key="image-key")
        )
    )
    client = SimpleNamespace(
        im=SimpleNamespace(v1=SimpleNamespace(image=SimpleNamespace(acreate=upload)))
    )
    download = AsyncMock(side_effect=AssertionError("Local images must not download"))
    monkeypatch.setattr(module, "download_image_by_url", download)
    chain = MessageChain(
        [Plain("before"), Image.fromFileSystem(str(image_path)), Plain("after")]
    )

    converted = await module.LarkMessageEvent._convert_to_lark(chain, client)

    assert converted == [
        [{"tag": "md", "text": "before"}],
        [{"tag": "img", "image_key": "image-key"}],
        [{"tag": "md", "text": "after"}],
    ]
    upload.assert_awaited_once()
    assert upload.await_args.args[0].request_body.image.getvalue() == image_bytes
    download.assert_not_awaited()
    assert image_path.read_bytes() == image_bytes


@pytest.mark.asyncio
async def test_separately_sent_media_is_not_downloaded_during_post_conversion():
    client = Mock()
    chain = MessageChain(
        [
            File(name="notes.txt", file="https://example.test/notes.txt"),
            Record(file="https://example.test/voice.wav"),
            Video(file="https://example.test/movie.mp4"),
            Plain("caption"),
        ]
    )

    assert await module.LarkMessageEvent._convert_to_lark(chain, client) == [
        [{"tag": "md", "text": "caption"}]
    ]
    assert client.mock_calls == []
