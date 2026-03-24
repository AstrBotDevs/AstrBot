from __future__ import annotations

import io
from types import SimpleNamespace

import pytest

from astrbot_sdk.runtime import transport as transport_module
from astrbot_sdk.runtime.transport import (
    StdioTransport,
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
async def test_stdio_read_file_loop_dispatches_messages_and_sets_closed() -> None:
    received: list[str] = []
    transport = StdioTransport(stdin=io.StringIO("line-1\nline-2\r\n"))
    transport.set_message_handler(lambda payload: _capture(received, payload))

    await transport._read_file_loop()

    assert received == ["line-1", "line-2"]
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


async def _capture(received: list[str], payload: str) -> None:
    received.append(payload)
