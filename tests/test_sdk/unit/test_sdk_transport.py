# ruff: noqa: SLF001
from __future__ import annotations

from types import SimpleNamespace

import pytest

from astrbot_sdk.runtime import transport as transport_module
from astrbot_sdk.runtime.transport import StdioTransport


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stdio_transport_retries_transient_windows_access_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    fake_process = SimpleNamespace()

    async def fake_create_subprocess_exec(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            error = PermissionError(13, "Access is denied")
            error.winerror = 5
            raise error
        return fake_process

    async def fake_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(
        transport_module.asyncio,
        "create_subprocess_exec",
        fake_create_subprocess_exec,
    )
    monkeypatch.setattr(transport_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(transport_module.sys, "platform", "win32")

    transport = StdioTransport(command=["python", "--version"])

    process = await transport._start_subprocess_with_retry()

    assert process is fake_process
    assert attempts == 2
