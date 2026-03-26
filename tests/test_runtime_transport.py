from __future__ import annotations

import asyncio
import io
from types import SimpleNamespace

import pytest

from astrbot_sdk.runtime import transport as transport_module
from astrbot_sdk.runtime.transport import (
    StdioTransport,
    WebSocketServerTransport,
    WebSocketClientTransport,
    _frame_stdio_payload,
)


@pytest.mark.unit
def test_frame_stdio_payload_rejects_embedded_newlines() -> None:
    with pytest.raises(ValueError, match="原始换行符"):
        _frame_stdio_payload("hello\nworld")


@pytest.mark.asyncio
async def test_stdio_read_process_loop_dispatches_messages_and_sets_closed() -> None:
    received: list[str] = []

    class _FakeStdout:
        def __init__(self) -> None:
            self._items = [b"first\r\n", b"second\n", b""]

        async def readline(self) -> bytes:
            return self._items.pop(0)

    transport = StdioTransport(command=["python", "-V"])
    transport._process = SimpleNamespace(stdout=_FakeStdout())
    transport.set_message_handler(lambda payload: _capture(received, payload))

    await transport._read_process_loop()

    assert received == ["first", "second"]
    assert transport._closed.is_set() is True


@pytest.mark.asyncio
async def test_stdio_wait_closed_unblocks_after_process_eof() -> None:
    class _FakeStdout:
        async def readline(self) -> bytes:
            return b""

    transport = StdioTransport(command=["python", "-V"])
    transport._process = SimpleNamespace(stdout=_FakeStdout())

    waiter = asyncio.create_task(transport.wait_closed())
    await transport._read_process_loop()
    await asyncio.wait_for(waiter, timeout=1)

    assert waiter.done() is True


@pytest.mark.asyncio
async def test_stdio_read_file_loop_dispatches_messages_and_sets_closed() -> None:
    received: list[str] = []
    transport = StdioTransport(stdin=io.StringIO("line-1\nline-2\r\n"))
    transport.set_message_handler(lambda payload: _capture(received, payload))

    await transport._read_file_loop()

    assert received == ["line-1", "line-2"]
    assert transport._closed.is_set() is True


@pytest.mark.asyncio
async def test_stdio_stop_kills_process_when_terminate_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class _FakeProcess:
        returncode = None
        stdin = None

        def terminate(self) -> None:
            calls.append("terminate")

        def kill(self) -> None:
            calls.append("kill")

        async def wait(self) -> None:
            calls.append("wait")

    async def fake_wait_for(awaitable, timeout: float):
        awaitable.close()
        del timeout
        raise asyncio.TimeoutError

    transport = StdioTransport(command=["python", "-V"])
    transport._process = _FakeProcess()
    monkeypatch.setattr(transport_module.asyncio, "wait_for", fake_wait_for)

    await transport.stop()

    assert calls == ["terminate", "kill", "wait"]
    assert transport._process is None
    assert transport._closed.is_set() is True


@pytest.mark.asyncio
async def test_websocket_client_read_loop_dispatches_text_and_binary_then_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[str] = []

    class _FakeWebSocket:
        closed = False

        def __init__(self) -> None:
            self._messages = iter(
                [
                    SimpleNamespace(type="text", data="hello"),
                    SimpleNamespace(type="binary", data=b"world"),
                ]
            )

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._messages)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

        def exception(self):
            return None

    fake_aiohttp = SimpleNamespace(
        WSMsgType=SimpleNamespace(TEXT="text", BINARY="binary", ERROR="error")
    )
    monkeypatch.setattr(transport_module, "_get_aiohttp", lambda: fake_aiohttp)

    transport = WebSocketClientTransport(url="ws://test")
    transport._ws = _FakeWebSocket()
    transport.set_message_handler(lambda payload: _capture(received, payload))

    await transport._read_loop()

    assert received == ["hello", "world"]
    assert transport._closed.is_set() is True


@pytest.mark.asyncio
async def test_websocket_server_send_raises_when_connection_is_gone_after_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = WebSocketServerTransport()
    transport._connected.set()
    transport._ws = SimpleNamespace(closed=True)

    async def fake_wait_for(awaitable, timeout: float):
        del timeout
        return await awaitable

    monkeypatch.setattr(transport_module.asyncio, "wait_for", fake_wait_for)

    with pytest.raises(RuntimeError, match="尚未连接"):
        await transport.send("payload")


async def _capture(received: list[str], payload: str) -> None:
    received.append(payload)
