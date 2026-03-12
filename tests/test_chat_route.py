import asyncio

import pytest

from astrbot.dashboard.routes.chat import _poll_webchat_stream_result


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
