from unittest.mock import patch

import pytest
from aiocqhttp import Event

import astrbot.api  # noqa: F401  # Initialize API before platform adapters.
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
    AiocqhttpAdapter,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message_type", "timestamp"),
    [
        ("group", 1793280000),
        ("private", 1793280000),
        ("group", None),
        ("group", -1),
        ("group", "invalid"),
    ],
)
async def test_message_preserves_protocol_time_or_falls_back(message_type, timestamp):
    payload = {
        "post_type": "message",
        "message_type": message_type,
        "self_id": 123,
        "user_id": 456,
        "group_id": 789,
        "sender": {"user_id": 456, "nickname": "Tester"},
        "message_id": 1,
        "message": [{"type": "text", "data": {"text": "hello"}}],
    }
    if timestamp is not None:
        payload["time"] = timestamp
    event = Event.from_payload(payload)
    adapter = AiocqhttpAdapter.__new__(AiocqhttpAdapter)
    with patch("astrbot.core.platform.astrbot_message.time.time", return_value=1793280300):
        message = await adapter.convert_message(event)

    expected = 1793280000 if timestamp == 1793280000 else 1793280300
    assert message.timestamp == expected
    assert message.message_str == "hello"
