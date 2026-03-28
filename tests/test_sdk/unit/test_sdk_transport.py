from __future__ import annotations

import asyncio
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
