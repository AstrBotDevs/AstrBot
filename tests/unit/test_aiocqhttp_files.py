from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest
from aiocqhttp import Event

import astrbot.api  # noqa: F401  # Initialize API before platform adapters.
from astrbot.core.message.components import File
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
    AiocqhttpAdapter,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("message_type", ["group", "private"])
@pytest.mark.parametrize("leading_text", [False, True])
async def test_each_file_segment_resolves_its_own_id(message_type, leading_text):
    segments = [
        {"type": "file", "data": {"file_id": "first", "file": "first.pdf"}},
        {"type": "file", "data": {"file_id": "second", "file": "second.xlsx"}},
    ]
    if leading_text:
        segments.insert(0, {"type": "text", "data": {"text": "Read these"}})
    event = Event.from_payload(
        {
            "post_type": "message",
            "message_type": message_type,
            "self_id": 123,
            "user_id": 456,
            "group_id": 789,
            "sender": {"user_id": 456, "nickname": "Tester"},
            "message_id": 1,
            "message": segments,
        }
    )
    adapter = AiocqhttpAdapter.__new__(AiocqhttpAdapter)
    adapter.bot = SimpleNamespace(
        call_action=AsyncMock(
            side_effect=[
                {"url": "https://example.com/first", "file_name": "first.pdf"},
                {"url": "https://example.com/second", "file_name": "second.xlsx"},
            ]
        )
    )
    result = await adapter._convert_handle_message_event(event)
    extra = {"group_id": 789} if message_type == "group" else {}
    adapter.bot.call_action.assert_has_awaits(
        [
            call(
                action=f"get_{message_type}_file_url",
                file_id=file_id,
                self_id=123,
                **extra,
            )
            for file_id in ["first", "second"]
        ]
    )
    files = [part for part in result.message if isinstance(part, File)]
    assert [(part.name, part.url) for part in files] == [
        ("first.pdf", "https://example.com/first"),
        ("second.xlsx", "https://example.com/second"),
    ]
