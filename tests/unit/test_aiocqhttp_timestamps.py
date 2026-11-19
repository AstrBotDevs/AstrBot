from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiocqhttp import Event

import astrbot.api  # noqa: F401  # Initialize API before platform adapters.
from astrbot.core.message.components import Reply
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
    AiocqhttpAdapter,
)


@pytest.fixture
def adapter():
    instance = AiocqhttpAdapter.__new__(AiocqhttpAdapter)
    instance.bot = SimpleNamespace(call_action=AsyncMock())
    return instance


@pytest.fixture
def payload():
    return {
        "post_type": "message",
        "message_type": "group",
        "self_id": 123,
        "user_id": 456,
        "group_id": 789,
        "sender": {"user_id": 456, "nickname": "Tester"},
        "message_id": 1,
        "message": [{"type": "text", "data": {"text": "Hello"}}],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("message_type", ["group", "private"])
@pytest.mark.parametrize("timestamp", [1700000000, "1700000000"])
async def test_message_preserves_original_timestamp(
    adapter, payload, monkeypatch, message_type, timestamp
):
    monkeypatch.setattr("time.time", lambda: 1800000000)
    payload.update(message_type=message_type, time=timestamp)

    result = await adapter.convert_message(Event.from_payload(payload))

    assert result.timestamp == 1700000000


@pytest.mark.asyncio
@pytest.mark.parametrize("message_type", ["group", "private"])
async def test_reply_preserves_its_own_timestamp_and_sender(
    adapter, payload, monkeypatch, message_type
):
    monkeypatch.setattr("time.time", lambda: 1800000000)
    quoted_payload = {
        **payload,
        "message_type": message_type,
        "message_id": 2,
        "time": 1700000000,
        "sender": {"user_id": 987, "nickname": "Quoted sender"},
    }
    adapter.bot.call_action.return_value = quoted_payload
    payload.update(
        message_type=message_type,
        time=1700086400,
        message=[
            {"type": "reply", "data": {"id": "2"}},
            {"type": "text", "data": {"text": "What about this?"}},
        ],
    )

    result = await adapter.convert_message(Event.from_payload(payload))

    reply = next(part for part in result.message if isinstance(part, Reply))
    assert result.timestamp == 1700086400
    assert result.sender.user_id == "456"
    assert reply.time == 1700000000
    assert str(reply.sender_id) == "987"
    assert reply.message_str == "Hello"
    adapter.bot.call_action.assert_awaited_once_with(
        action="get_msg", message_id=2, self_id=123
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("timestamp", [None, "invalid", "", 0, -1, True, [], {}])
async def test_invalid_message_time_keeps_receive_time(
    adapter, payload, monkeypatch, timestamp
):
    monkeypatch.setattr("time.time", lambda: 1800000000)
    if timestamp is not None:
        payload["time"] = timestamp

    result = await adapter.convert_message(Event.from_payload(payload))

    assert result.timestamp == 1800000000


@pytest.mark.asyncio
@pytest.mark.parametrize("timestamp", [None, "invalid", "", 0, -1, True, [], {}])
async def test_invalid_reply_time_is_unknown(adapter, payload, monkeypatch, timestamp):
    monkeypatch.setattr("time.time", lambda: 1800000000)
    quoted_payload = {**payload, "message_id": 2}
    if timestamp is not None:
        quoted_payload["time"] = timestamp
    adapter.bot.call_action.return_value = quoted_payload
    payload.update(
        time=1700086400,
        message=[{"type": "reply", "data": {"id": "2"}}],
    )

    result = await adapter.convert_message(Event.from_payload(payload))

    reply = next(part for part in result.message if isinstance(part, Reply))
    assert reply.time == 0
    assert reply.message_str == "Hello"
    assert result.timestamp == 1700086400
