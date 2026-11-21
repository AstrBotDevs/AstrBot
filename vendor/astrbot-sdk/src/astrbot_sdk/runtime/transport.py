"""Frame transports for the SDK protocol.

The protocol frames are self-delimiting JSON documents, so any ordered,
reliable byte or message channel can carry them. This module provides the
transports: stdio pipes for host-spawned local runners, asyncio streams for
the Host side of those pipes, and WebSocket connections for runners the
Host cannot spawn (remote machines, containers, future non-Python SDKs).
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any, BinaryIO, Protocol

from ..errors import HostUnavailable
from ..protocol import MAX_FRAME_BYTES


class FrameTransport(Protocol):
    """Ordered, reliable frame channel used by runners and Host clients."""

    async def read(self) -> bytes | None:
        """Read the next frame payload; None means the channel is closed."""
        ...

    async def write(self, data: bytes) -> None:
        """Write one frame payload atomically."""
        ...

    async def close(self) -> None:
        """Close the channel; safe to call more than once."""
        ...

    async def wait_closed(self) -> None:
        """Wait until the channel is closed by either side."""
        ...

    @property
    def closed(self) -> bool:
        """Whether the channel is closed."""
        ...


class StdioTransport:
    """Runner-side transport over blocking binary file objects."""

    def __init__(self, reader: BinaryIO, writer: BinaryIO) -> None:
        """Wrap the stdin/stdout binary streams of the Runner process."""
        self._reader = reader
        self._writer = writer
        self._write_lock = asyncio.Lock()
        self._closed = asyncio.Event()

    async def read(self) -> bytes | None:
        line = await asyncio.to_thread(
            self._reader.readline,
            MAX_FRAME_BYTES + 1,
        )
        if not line:
            self._closed.set()
            return None
        return line

    async def write(self, data: bytes) -> None:
        async with self._write_lock:
            try:
                self._writer.write(data)
                self._writer.flush()
            except (BrokenPipeError, ConnectionError) as exc:
                self._closed.set()
                raise HostUnavailable("stdio transport is closed") from exc

    async def close(self) -> None:
        self._closed.set()

    async def wait_closed(self) -> None:
        await self._closed.wait()

    @property
    def closed(self) -> bool:
        return self._closed.is_set()


class StreamTransport:
    """Host-side transport over asyncio subprocess streams."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Wrap the Runner process stdout/stdin asyncio streams."""
        self._reader = reader
        self._writer = writer
        self._write_lock = asyncio.Lock()
        self._closed = asyncio.Event()

    async def read(self) -> bytes | None:
        line = await self._reader.readline()
        if not line:
            self._closed.set()
            return None
        return line

    async def write(self, data: bytes) -> None:
        if self._writer.is_closing():
            raise HostUnavailable("stream transport is closed")
        try:
            async with self._write_lock:
                self._writer.write(data)
                await self._writer.drain()
        except (BrokenPipeError, ConnectionError) as exc:
            self._closed.set()
            raise HostUnavailable("stream transport is closed") from exc

    async def close(self) -> None:
        if not self._writer.is_closing():
            self._writer.close()
            with contextlib.suppress(BrokenPipeError, ConnectionError):
                await self._writer.wait_closed()
        self._closed.set()

    async def wait_closed(self) -> None:
        await self._closed.wait()

    @property
    def closed(self) -> bool:
        return self._closed.is_set()


class WebSocketTransport:
    """Transport over one WebSocket connection (either peer role).

    Each protocol frame travels as one WebSocket text message. Reads return
    None on a clean close and raise ``ConnectionClosedError`` on abnormal
    closure so callers can log the close code and reason.
    """

    def __init__(self, connection: Any) -> None:
        """Wrap one connected ``websockets`` client or server connection."""
        self._connection = connection
        self._write_lock = asyncio.Lock()
        self._closed = asyncio.Event()

    async def read(self) -> bytes | None:
        from websockets.exceptions import ConnectionClosed, ConnectionClosedOK

        try:
            message = await self._connection.recv()
        except ConnectionClosedOK:
            self._closed.set()
            return None
        except ConnectionClosed:
            self._closed.set()
            raise
        if isinstance(message, str):
            return message.encode("utf-8")
        return message

    async def write(self, data: bytes) -> None:
        from websockets.exceptions import ConnectionClosed

        try:
            async with self._write_lock:
                await self._connection.send(data.decode("utf-8"))
        except ConnectionClosed as exc:
            self._closed.set()
            raise HostUnavailable("websocket transport is closed") from exc

    async def close(self) -> None:
        with contextlib.suppress(Exception):
            await self._connection.close()
        self._closed.set()

    async def wait_closed(self) -> None:
        # websockets completes the closing handshake in the background, so
        # this resolves even when no read loop is consuming the socket
        # (a second recv consumer would race the read loop).
        await self._connection.wait_closed()
        self._closed.set()

    @property
    def closed(self) -> bool:
        if self._closed.is_set():
            return True
        from websockets.protocol import State

        return self._connection.state is State.CLOSED
