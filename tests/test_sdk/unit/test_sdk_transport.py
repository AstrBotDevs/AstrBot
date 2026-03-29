from __future__ import annotations

import asyncio
import io
import sys

import pytest
from astrbot_sdk.runtime.transport import (
    STDIO_SUBPROCESS_STREAM_LIMIT,
    StdioTransport,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stdio_transport_uses_large_stream_limit(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class DummyProcess:
        stdin = None
        stdout = None

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return DummyProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    transport = StdioTransport(command=[sys.executable, "-c", "print('ok')"])

    process = await transport._start_subprocess_with_retry()  # noqa: SLF001

    assert isinstance(process, DummyProcess)
    assert captured["kwargs"]["limit"] == STDIO_SUBPROCESS_STREAM_LIMIT


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stdio_transport_drops_handler_exception_and_keeps_reading() -> None:
    payload = b"5\nfirst6\nsecond"
    transport = StdioTransport(
        stdin=type("DummyStdin", (), {"buffer": io.BytesIO(payload)})()
    )
    received: list[str] = []

    async def handler(message: str) -> None:
        received.append(message)
        if len(received) == 1:
            raise RuntimeError("boom")

    transport.set_message_handler(handler)

    await transport._read_file_loop()  # noqa: SLF001

    assert received == ["first", "second"]
