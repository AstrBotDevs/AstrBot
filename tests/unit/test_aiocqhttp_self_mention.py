"""Verify configurable self-mention text without losing structured mentions."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiocqhttp import Event

from astrbot.core.message.components import At
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
    AiocqhttpAdapter,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("strip_self_mention", [None, True, False])
@pytest.mark.parametrize("mention_ids", [[123], [456, 123, 789], [123, 123, 456]])
@pytest.mark.parametrize("separate_mentions", [False, True])
async def test_self_mention_text_option(
    strip_self_mention, mention_ids, separate_mentions
):
    """Retain all mention targets when disabled and preserve legacy defaults."""
    adapter = AiocqhttpAdapter.__new__(AiocqhttpAdapter)
    adapter.config = (
        {} if strip_self_mention is None else {"strip_self_mention": strip_self_mention}
    )
    adapter.bot = SimpleNamespace(
        call_action=AsyncMock(side_effect=lambda **kwargs: {"card": str(kwargs["user_id"])})
    )
    segments = []
    for mention_id in mention_ids:
        segments.append({"type": "at", "data": {"qq": str(mention_id)}})
        if separate_mentions:
            segments.append({"type": "text", "data": {"text": " "}})
    segments.append({"type": "text", "data": {"text": "roll call"}})
    event = Event(
        {
            "post_type": "message",
            "message_type": "group",
            "self_id": 123,
            "user_id": 42,
            "group_id": 99,
            "message_id": 1,
            "sender": {"user_id": 42, "nickname": "User"},
            "message": segments,
        }
    )

    result = await adapter._convert_handle_message_event(event)

    assert [str(c.qq) for c in result.message if isinstance(c, At)] == [
        str(mention_id) for mention_id in mention_ids
    ]
    self_mentions = mention_ids.count(123)
    if strip_self_mention is not False:
        self_mentions = 0 if separate_mentions else self_mentions - 1
    assert result.message_str.count("@123(123)") == self_mentions
    for mention_id in (456, 789):
        assert result.message_str.count(f"@{mention_id}({mention_id})") == mention_ids.count(
            mention_id
        )
    assert result.message_str.endswith("roll call")
