"""
ACP (AstrBot Communication Protocol) client implementation.

ACP is a client-server protocol for inter-service communication,
similar to MCP but designed specifically for AstrBot's architecture.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from astrbot import logger
from astrbot._internal.abc.acp.base_astrbot_acp_client import BaseAstrbotAcpClient

log = logger


class AstrbotAcpClient(BaseAstrbotAcpClient):
    """
    ACP client for communicating with ACP servers.

    The orchestrator acts as an ACP client, connecting to external
    ACP-compatible services.
    """

    def __init__(self) -> None:
        self._connected = False
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._server_url: str | None = None
        self._pending_requests: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._request_id = 0
        self._reader_task: asyncio.Task[None] | None = None

    @property
    def connected(self) -> bool:
        """True if connected to an ACP server."""
        return self._connected

    async def connect(self) -> None:
        """
        Connect to configured ACP servers.

        ACP servers can be accessed via TCP (host:port) or Unix socket.
        """
        log.debug("ACP client connecting...")
        # TODO: Load ACP server configurations
        self._connected = True
        log.info("ACP client initialized.")

    async def connect_to_server(self, host: str, port: int) -> None:
        """
        Connect to an ACP server via TCP.

        Args:
            host: Server hostname or IP
            port: Server port
        """
        self._server_url = f"{host}:{port}"
        self._reader, self._writer = await asyncio.open_connection(host, port)
        self._connected = True

        # Start reading responses
        self._reader_task = asyncio.create_task(self._read_messages())

        log.info(f"ACP client connected to {self._server_url}")

    async def connect_to_unix_socket(self, socket_path: str) -> None:
        """
        Connect to an ACP server via Unix socket.

        Args:
            socket_path: Path to the Unix socket
        """
        self._server_url = f"unix://{socket_path}"
        self._reader, self._writer = await asyncio.open_unix_connection(socket_path)
        self._connected = True

        self._reader_task = asyncio.create_task(self._read_messages())

        log.info(f"ACP client connected to {self._server_url}")

    async def _read_messages(self) -> None:
        """Background task to read ACP messages."""
        if not self._reader:
            return

        buffer = b""
        while self._connected:
            try:
                data = await self._reader.read(4096)
                if not data:
                    break
                buffer += data

                while True:
                    header_end = buffer.find(b"\n")
                    if header_end == -1:
                        break

                    try:
                        header = json.loads(buffer[:header_end].decode("utf-8"))
                    except json.JSONDecodeError:
                        buffer = buffer[header_end + 1 :]
                        continue

                    content_length = header.get("content-length", 0)
                    if content_length == 0 or len(buffer) < header_end + 1 + content_length:
                        break

                    content = buffer[header_end + 1 : header_end + 1 + content_length]
                    buffer = buffer[header_end + 1 + content_length :]

                    message = json.loads(content.decode("utf-8"))

                    if "id" in message:
                        request_id = str(message["id"])
                        future = self._pending_requests.pop(request_id, None)
                        if future and not future.done():
                            if "error" in message:
                                future.set_exception(Exception(str(message["error"])))
                            else:
                                future.set_result(message.get("result", {}))
                    else:
                        await self._handle_notification(message)

            except Exception as e:
                if self._connected:
                    log.error(f"ACP read error: {e}")
                break

    async def _handle_notification(self, notification: dict[str, Any]) -> None:
        """Handle incoming ACP notifications."""
        method = notification.get("method", "")
        log.debug(f"ACP notification: {method}")

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any]
    ) -> Any:
        """
        Call a tool on an ACP server.

        Args:
            server_name: Name of the ACP server
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool call result
        """
        if not self._connected:
            raise RuntimeError("ACP client is not connected")

        request_id = str(self._request_id)
        self._request_id += 1

        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": f"{server_name}/{tool_name}",
            "params": arguments,
        }

        future: asyncio.Future[dict[str, Any]] = asyncio.Future()
        self._pending_requests[request_id] = future

        await self._send_message(message)
        return await future

    async def _send_message(self, message: dict[str, Any]) -> None:
        """Send an ACP message."""
        if not self._writer:
            raise RuntimeError("ACP client not connected")

        content = json.dumps(message)
        header = json.dumps({"content-length": len(content)}) + "\n"

        self._writer.write((header + content).encode())
        await self._writer.drain()

    async def send_notification(
        self, method: str, params: dict[str, Any] | None = None
    ) -> None:
        """Send a one-way notification to the server."""
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }
        await self._send_message(message)

    async def shutdown(self) -> None:
        """Shutdown the ACP client connection."""
        self._connected = False

        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass

        for future in self._pending_requests.values():
            if not future.done():
                future.cancel()
        self._pending_requests.clear()

        log.info("ACP client shut down.")
