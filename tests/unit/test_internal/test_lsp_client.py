from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anyio.abc import ByteReceiveStream

from astrbot._internal.protocols.lsp.client import AstrbotLspClient


class FakeReader(ByteReceiveStream):
    def __init__(self, receive_mock: AsyncMock) -> None:
        self._receive_mock = receive_mock

    async def receive(self, max_bytes: int = 65536) -> bytes:
        del max_bytes
        return await self._receive_mock()

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_lsp_read_responses_failure_disconnects_and_logs():
    """Test reader failures are handled inside _read_responses."""
    client = AstrbotLspClient()
    client._connected = True
    client._reader = FakeReader(AsyncMock(side_effect=RuntimeError("reader crashed")))

    with patch("astrbot._internal.protocols.lsp.client.log") as mock_log:
        await client._read_responses()

    assert client.connected is False
    mock_log.error.assert_called_once()


@pytest.mark.asyncio
async def test_lsp_read_responses_unexpected_exit_disconnects_and_warns():
    """Test non-cancelled reader exit updates connection state."""
    client = AstrbotLspClient()
    client._connected = True
    client._reader = FakeReader(AsyncMock(return_value=b""))

    with patch("astrbot._internal.protocols.lsp.client.log") as mock_log:
        await client._read_responses()

    assert client.connected is False
    mock_log.warning.assert_called_once()


@pytest.mark.asyncio
async def test_lsp_read_responses_clears_reader_task_reference_on_exit():
    """Test _read_responses clears the stored task reference when it exits."""
    client = AstrbotLspClient()
    client._connected = True
    client._reader = FakeReader(AsyncMock(return_value=b""))

    task = asyncio.create_task(client._read_responses())
    client._reader_task = task

    await task

    assert client._reader_task is None


@pytest.mark.asyncio
async def test_lsp_stop_reader_task_swallows_failed_reader_exceptions():
    """Test reader teardown does not re-raise prior reader failures."""
    client = AstrbotLspClient()

    async def fail_reader() -> None:
        raise RuntimeError("reader crashed")

    client._reader_task = asyncio.create_task(fail_reader())
    await asyncio.sleep(0)

    await client._stop_reader_task()
    assert client._reader_task is None


@pytest.mark.asyncio
async def test_lsp_connect_to_server_cancels_previous_reader_task_before_restart():
    """Test reconnect tears down an existing reader task before replacing it."""
    client = AstrbotLspClient()
    fake_process = SimpleNamespace(stdout=MagicMock(), stdin=MagicMock())
    first_reader_cancelled = asyncio.Event()
    first_reader_started = asyncio.Event()

    async def first_reader() -> None:
        first_reader_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            first_reader_cancelled.set()
            raise

    with (
        patch(
            "astrbot._internal.protocols.lsp.client.anyio.open_process",
            AsyncMock(return_value=fake_process),
        ),
        patch.object(client, "send_request", AsyncMock(return_value={})),
        patch.object(client, "send_notification", AsyncMock()),
    ):
        client._read_responses = first_reader  # type: ignore[method-assign]
        await client.connect_to_server(["python", "first_lsp.py"], "file:///tmp")
        await asyncio.wait_for(first_reader_started.wait(), timeout=1)
        assert client.connected is True

        second_reader = AsyncMock(return_value=None)
        client._read_responses = second_reader  # type: ignore[method-assign]
        await client.connect_to_server(["python", "second_lsp.py"], "file:///tmp")
        await asyncio.sleep(0)

        assert first_reader_cancelled.is_set() is True
        assert client.connected is True


@pytest.mark.asyncio
async def test_lsp_stop_reader_task_does_not_await_current_task():
    """Test stopping the reader from within itself does not self-await."""
    client = AstrbotLspClient()
    done = asyncio.Event()

    async def stop_self() -> None:
        client._reader_task = asyncio.current_task()
        await client._stop_reader_task()
        done.set()

    task = asyncio.create_task(stop_self())
    await asyncio.wait_for(done.wait(), timeout=1)
    await task
