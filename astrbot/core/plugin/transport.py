"""ABP Transport Implementations"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Any

import anyio

logger = logging.getLogger("astrbot.plugin.transport")


class Transport(ABC):
    """Base transport class."""

    @abstractmethod
    async def send(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send JSON-RPC request and receive response."""
        pass

    @abstractmethod
    async def notify(self, method: str, params: dict[str, Any]) -> None:
        """Send JSON-RPC notification (no response)."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the transport."""
        pass


class StdioTransport(Transport):
    """Stdio transport for subprocess communication.

    Messages are sent as single-line JSON.
    """

    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self._process = process
        self._lock = asyncio.Lock()

    async def send(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send request via stdin and read from stdout."""
        request = {
            "jsonrpc": "2.0",
            "id": str(id(params)),
            "method": method,
            "params": params,
        }
        line = json.dumps(request, ensure_ascii=False)
        async with self._lock:
            self._process.stdin.write((line + "\n").encode("utf-8"))
            await self._process.stdin.drain()
            response_line = await self._process.stdout.readline()
        if not response_line:
            raise RuntimeError("Plugin process closed unexpectedly")
        response = json.loads(response_line.decode("utf-8"))
        if "error" in response:
            raise RuntimeError(f"JSON-RPC error: {response['error']}")
        return response.get("result", {})

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        """Send notification via stdin."""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        line = json.dumps(notification, ensure_ascii=False)
        async with self._lock:
            self._process.stdin.write((line + "\n").encode("utf-8"))
            await self._process.stdin.drain()

    async def close(self) -> None:
        """Terminate the subprocess."""
        self._process.terminate()
        try:
            await asyncio.wait_for(self._process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            self._process.kill()


class UnixSocketTransport(Transport):
    """Unix Socket transport.

    Uses Content-Length framing protocol.
    """

    def __init__(self, socket_path: str) -> None:
        self._socket_path = socket_path
        self._reader: anyio.abc.SocketStream | None = None
        self._writer: anyio.abc.SocketStream | None = None

    async def connect(self) -> None:
        """Connect to the Unix socket."""
        try:
            self._reader, self._writer = await anyio.connect_unix(self._socket_path)
        except Exception as e:
            raise RuntimeError(f"Failed to connect to {self._socket_path}: {e}")

    async def send(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send request and receive response."""
        if not self._writer:
            await self.connect()
        assert self._writer
        assert self._reader

        request = {
            "jsonrpc": "2.0",
            "id": str(id(params)),
            "method": method,
            "params": params,
        }
        content = json.dumps(request, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(content)}\r\n\r\n".encode()

        await self._writer.send_all(header + content)

        # Read response header
        header_data = b""
        while b"\r\n\r\n" not in header_data:
            chunk = await self._reader.receive_some(1024)
            if not chunk:
                raise RuntimeError("Connection closed")
            header_data += chunk

        header_str = header_data.decode("utf-8")
        content_length = 0
        for line in header_str.split("\r\n"):
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":")[1].strip())

        # Read response body
        body_data = b""
        while len(body_data) < content_length:
            chunk = await self._reader.receive_some(content_length - len(body_data))
            if not chunk:
                raise RuntimeError("Connection closed")
            body_data += chunk

        response = json.loads(body_data.decode("utf-8"))
        if "error" in response:
            raise RuntimeError(f"JSON-RPC error: {response['error']}")
        return response.get("result", {})

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        """Send notification (no response expected)."""
        if not self._writer:
            await self.connect()
        assert self._writer

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        content = json.dumps(notification, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(content)}\r\n\r\n".encode()
        await self._writer.send_all(header + content)

    async def close(self) -> None:
        """Close the socket connection."""
        if self._writer:
            await self._writer.aclose()
            self._writer = None
            self._reader = None


class HttpTransport(Transport):
    """HTTP/SSE transport for remote plugins."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._client: anyio.http.websockets.client.ClientSession | None = None

    async def connect(self) -> None:
        """Initialize HTTP client."""
        # For now, use aiohttp-like interface via anyio
        pass

    async def send(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send HTTP POST request."""
        request = {
            "jsonrpc": "2.0",
            "id": str(id(params)),
            "method": method,
            "params": params,
        }

        async with anyio.open_http_connect(self._url) as (reader, writer):
            body = json.dumps(request).encode("utf-8")
            writer.write(
                f"POST / HTTP/1.1\r\n"
                f"Host: {self._url}\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"\r\n".encode()
            )
            writer.write(body)
            await writer.aclose()

            # Read response
            response = await reader.read()
            # Simple parsing - in reality would need proper HTTP parsing
            return json.loads(response.decode("utf-8")).get("result", {})

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        """Send notification via HTTP POST."""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        body = json.dumps(notification).encode("utf-8")
        async with anyio.open_http_connect(self._url) as (_reader, writer):
            writer.write(
                f"POST / HTTP/1.1\r\n"
                f"Host: {self._url}\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"\r\n".encode()
            )
            writer.write(body)
            await writer.aclose()

    async def close(self) -> None:
        """Close the transport."""
        if self._client:
            await self._client.aclose()
            self._client = None
