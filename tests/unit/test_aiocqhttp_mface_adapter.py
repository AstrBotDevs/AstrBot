import pytest
from aiocqhttp import Event

from astrbot.api.message_components import Image, Plain
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
    AiocqhttpAdapter,
)


def _message_event(segment_type: str, data: dict) -> Event:
    """Build a minimal OneBot group message event.

    Args:
        segment_type: OneBot message segment type.
        data: Segment payload.

    Returns:
        Parsed aiocqhttp event.
    """

    return Event.from_payload(
        {
            "time": 1,
            "self_id": 2860786196,
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "message_id": 123,
            "group_id": 895538565,
            "user_id": 2831304142,
            "sender": {"user_id": 2831304142, "nickname": "tester", "card": ""},
            "message": [{"type": segment_type, "data": data}],
            "raw_message": "",
        }
    )


@pytest.mark.asyncio
async def test_mface_url_is_converted_to_standard_image() -> None:
    adapter = AiocqhttpAdapter.__new__(AiocqhttpAdapter)
    event = _message_event(
        "mface",
        {"emoji_id": "1", "cdn_url": "https://example.com/sticker.png"},
    )

    message = await adapter._convert_handle_message_event(event)

    assert len(message.message) == 1
    assert isinstance(message.message[0], Image)
    assert message.message[0].file == "https://example.com/sticker.png"


@pytest.mark.asyncio
async def test_mface_without_url_is_not_silently_dropped() -> None:
    adapter = AiocqhttpAdapter.__new__(AiocqhttpAdapter)
    event = _message_event("marketface", {"emoji_id": "1"})

    message = await adapter._convert_handle_message_event(event)

    assert len(message.message) == 1
    assert isinstance(message.message[0], Plain)
    assert message.message_str == "[QQ表情]"
