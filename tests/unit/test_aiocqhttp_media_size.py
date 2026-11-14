"""Regression tests for aiocqhttp media that exceeds the WebSocket frame limit.

aiohttp caps incoming WebSocket messages at 4 MB by default. aiocqhttp sends
each OneBot API call as one JSON frame, so base64 media larger than the limit
disconnects the reverse WebSocket instead of reaching the protocol side.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import astrbot.core.message.components as Comp
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.sources.aiocqhttp import aiocqhttp_message_event
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

MAX_WS_MESSAGE_BYTES = 4 * 1024 * 1024


class OversizedImage(Comp.Image):
    async def convert_to_base64(self) -> str:
        return "A" * MAX_WS_MESSAGE_BYTES


class SmallImage(Comp.Image):
    async def convert_to_base64(self) -> str:
        return "AAAA"


class OversizedRecord(Comp.Record):
    async def convert_to_base64(self) -> str:
        return "A" * MAX_WS_MESSAGE_BYTES


@pytest.fixture
def fake_logger(monkeypatch):
    logger = SimpleNamespace(
        debug=Mock(),
        info=Mock(),
        warning=Mock(),
        error=Mock(),
    )
    monkeypatch.setattr(aiocqhttp_message_event, "logger", logger)
    return logger


@pytest.mark.asyncio
async def test_oversized_base64_media_is_not_dispatched_as_ws_frame(fake_logger):
    bot = SimpleNamespace(
        send_private_msg=AsyncMock(),
        send_group_msg=AsyncMock(),
    )

    with pytest.raises(ValueError, match="4 MB"):
        await AiocqhttpMessageEvent.send_message(
            bot=bot,
            message_chain=MessageChain([OversizedImage(file="base64://AAAA")]),
            is_group=False,
            session_id="123456",
        )

    bot.send_private_msg.assert_not_awaited()
    fake_logger.error.assert_called_once()


@pytest.mark.asyncio
async def test_oversized_media_with_local_path_uses_file_uri(fake_logger, tmp_path):
    media_path = tmp_path / "large.gif"
    media_path.write_bytes(b"GIF89a")
    segment = OversizedImage(file=str(media_path), path=str(media_path))

    data = await AiocqhttpMessageEvent._from_segment_to_dict(segment)

    assert data == {"type": "image", "data": {"file": media_path.as_uri()}}
    fake_logger.warning.assert_called_once()
    fake_logger.error.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("candidate_kind", ["missing", "directory"])
async def test_oversized_media_with_invalid_local_path_raises(
    fake_logger, tmp_path, candidate_kind
):
    candidate = tmp_path / candidate_kind
    if candidate_kind == "directory":
        candidate.mkdir()
    segment = OversizedImage(file=str(candidate), path=str(candidate))

    with pytest.raises(ValueError, match="4 MB"):
        await AiocqhttpMessageEvent._from_segment_to_dict(segment)

    fake_logger.error.assert_called_once()
    fake_logger.warning.assert_not_called()


@pytest.mark.asyncio
async def test_oversized_media_with_http_url_reuses_the_url(fake_logger):
    url = "https://example.com/large.gif"
    segment = OversizedImage(file=url)

    data = await AiocqhttpMessageEvent._from_segment_to_dict(segment)

    assert data == {"type": "image", "data": {"file": url}}
    fake_logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_oversized_record_without_reference_raises(fake_logger):
    with pytest.raises(ValueError, match="4 MB"):
        await AiocqhttpMessageEvent._from_segment_to_dict(
            OversizedRecord(file="base64://AAAA")
        )

    fake_logger.error.assert_called_once()


@pytest.mark.asyncio
async def test_small_image_keeps_base64_payload(fake_logger):
    data = await AiocqhttpMessageEvent._from_segment_to_dict(
        SmallImage(file="base64://AAAA")
    )

    assert data == {"type": "image", "data": {"file": "base64://AAAA"}}
    fake_logger.warning.assert_not_called()
    fake_logger.error.assert_not_called()
