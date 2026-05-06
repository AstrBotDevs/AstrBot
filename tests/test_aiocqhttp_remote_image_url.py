import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Image, Record
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)


@pytest.mark.asyncio
async def test_aiocqhttp_remote_image_url_defaults_to_base64(monkeypatch):
    image = Image.fromURL("https://example.com/cat.png")

    async def fake_base64(self):
        return "image-data"

    monkeypatch.setattr(Image, "convert_to_base64", fake_base64)

    payload = await AiocqhttpMessageEvent._parse_onebot_json(MessageChain([image]))

    assert payload == [{"type": "image", "data": {"file": "base64://image-data"}}]


@pytest.mark.asyncio
async def test_aiocqhttp_remote_image_url_opt_in(monkeypatch):
    image = Image.fromURL("https://example.com/cat.png")

    async def should_not_convert(self):
        raise AssertionError("remote image URL should be passed through")

    monkeypatch.setattr(Image, "convert_to_base64", should_not_convert)

    payload = await AiocqhttpMessageEvent._parse_onebot_json(
        MessageChain([image]).use_remote_image_url(True)
    )

    assert payload == [
        {"type": "image", "data": {"file": "https://example.com/cat.png"}}
    ]


@pytest.mark.asyncio
async def test_aiocqhttp_remote_image_url_does_not_affect_records(monkeypatch):
    record = Record.fromURL("https://example.com/cat.mp3")

    async def fake_base64(self):
        return "record-data"

    monkeypatch.setattr(Record, "convert_to_base64", fake_base64)

    payload = await AiocqhttpMessageEvent._parse_onebot_json(
        MessageChain([record]).use_remote_image_url(True)
    )

    assert payload == [{"type": "record", "data": {"file": "base64://record-data"}}]
