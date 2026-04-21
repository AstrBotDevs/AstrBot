import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from astrbot.dashboard.routes.chat import _poll_webchat_stream_result
from astrbot.dashboard.routes.message_events import build_message_saved_event
from astrbot.core.utils.datetime_utils import to_utc_isoformat


class _QueueThatRaises:
    def __init__(self, exc: BaseException):
        self._exc = exc

    async def get(self):
        raise self._exc


class _QueueWithResult:
    def __init__(self, result):
        self._result = result

    async def get(self):
        return self._result


@pytest.mark.asyncio
async def test_poll_webchat_stream_result_breaks_on_cancelled_error():
    result, should_break = await _poll_webchat_stream_result(
        _QueueThatRaises(asyncio.CancelledError()),
        "alice",
    )

    assert result is None
    assert should_break is True


@pytest.mark.asyncio
async def test_poll_webchat_stream_result_continues_on_generic_exception():
    result, should_break = await _poll_webchat_stream_result(
        _QueueThatRaises(RuntimeError("boom")),
        "alice",
    )

    assert result is None
    assert should_break is False


@pytest.mark.asyncio
async def test_poll_webchat_stream_result_returns_queue_payload():
    payload = {"type": "end", "data": ""}

    result, should_break = await _poll_webchat_stream_result(
        _QueueWithResult(payload),
        "alice",
    )

    assert result == payload
    assert should_break is False


@pytest.mark.parametrize("chat_mode", [False, True])
def test_build_message_saved_event_includes_refs(chat_mode: bool):
    saved_record = SimpleNamespace(
        id=42,
        created_at=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
    )
    refs = {
        "used": [
            {
                "index": "abcd.1",
                "url": "https://example.com",
                "title": "Example",
            }
        ]
    }

    payload = build_message_saved_event(saved_record, refs, chat_mode=chat_mode)

    expected = {
        "type": "message_saved",
        "data": {
            "id": 42,
            "created_at": to_utc_isoformat(saved_record.created_at),
            "refs": refs,
        },
    }
    if chat_mode:
        expected["ct"] = "chat"

    assert payload == expected
