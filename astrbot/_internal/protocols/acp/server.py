"""
ACP (AstrBot Communication Protocol) server implementation.

ACP servers listen for connections from ACP clients and provide
services/tools to the orchestrator.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

from astrbot import logger
from astrbot._internal.abc.acp.base_astrbot_acp_server import BaseAstrbotAcpServer

log = logger


class AstrbotAcpServer(BaseAstrbotAcpServer):
    """
    ACP server for accepting connections from ACP clients.

    ACP servers expose tools/notifications that can be called by clients.
    """

    def __init__(self) -> None:
        self._running = False
        self._host: str = "127.0.0.1"
        self._port: int = 8765
        self._server: asyncio.Server | None = None
        self._clients: set[tuple[asyncio.StreamReader, asyncio.StreamWriter]] = set()
        self._tool_handlers: dict[str, Callable[..., Any]] = {}
        self._notification_handlers: dict[str, Callable[..., Any]] = {}

    def register_tool(self, name: str, handler: Callable[..., Any]) -> None:
        """
        Register a tool handler.

        Args:
            name: Tool name
            handler: Async callable that handles tool calls
        """
        self._tool_handlers[name] = handler
        log.debug(f"ACP server registered tool: {name}")

    def register_notification_handler(
        self, name: str, handler: Callable[..., Any]
    ) -> None:
        """
        Register a notification handler.

        Args:
            name: Notification method name
            handler: Async callable that handles notifications
        """
        self._notification_handlers[name] = handler
        log.debug(f"ACP server registered notification handler: {name}")

    async def start(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        """
        Start the ACP server.

        Args:
            host: Host to bind to
            port: Port to listen on
        """
        self._host = host
        self._port = port
        self._server = await asyncio.start_server(
            self._handle_client,
            host=host,
            port=port,
        )
        self._running = True
        log.info(f"ACP server listening on {host}:{port}")

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle an incoming ACP client connection."""
        addr = writer.get_extra_info("peername")
        log.debug(f"ACP client connected: {addr}")
        self._clients.add((reader, writer))

        buffer = b""
        try:
            while self._running:
                try:
                    data = await reader.read(4096)
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
                        if (
                            content_length == 0
                            or len(buffer) < header_end + 1 + content_length
                        ):
                            break

                        content = buffer[
                            header_end + 1 : header_end + 1 + content_length
                        ]
                        buffer = buffer[header_end + 1 + content_length :]

                        message = json.loads(content.decode("utf-8"))
                        response = await self._handle_message(message)

                        if response:
                            content = json.dumps(response)
                            resp_header = (
                                json.dumps({"content-length": len(content)}) + "\n"
                            )
                            writer.write(resp_header.encode() + content.encode())
                            await writer.drain()

                except Exception as e:
                    log.error(f"ACP client error ({addr}): {e}")
                    break

        finally:
            self._clients.discard((reader, writer))
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            log.debug(f"ACP client disconnected: {addr}")

    async def _handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Handle an incoming ACP message."""
        method = message.get("method", "")
        msg_id = message.get("id")
        params = message.get("params", {})

        # Check if it's a notification (no id) or request (has id)
        if msg_id is None:
            # Notification
            handler = self._notification_handlers.get(method)
            if handler:
                try:
                    await handler(params)
                except Exception as e:
                    log.error(f"ACP notification handler error ({method}): {e}")
            return None

        # Request
        result = None
        error = None

        handler = self._tool_handlers.get(method)
        if handler:
            try:
                result = await handler(params)
            except Exception as e:
                error = str(e)
                log.error(f"ACP tool handler error ({method}): {e}")
        else:
            error = f"Unknown method: {method}"

        response: dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id}
        if error:
            response["error"] = {"code": -32601, "message": error}
        else:
            response["result"] = result

        return response

    async def broadcast_notification(self, method: str, params: dict[str, Any]) -> None:
        """
        Broadcast a notification to all connected clients.

        Args:
            method: Notification method name
            params: Notification parameters
        """
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        content = json.dumps(message)
        header = json.dumps({"content-length": len(content)}) + "\n"
        data = header.encode() + content.encode()

        for reader, writer in list(self._clients):
            try:
                writer.write(data)
                await writer.drain()
            except Exception as e:
                log.warning(f"Failed to broadcast to client: {e}")

    async def shutdown(self) -> None:
        """Shutdown the ACP server."""
        self._running = False

        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        for reader, writer in list(self._clients):
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
        self._clients.clear()

        log.info("ACP server shut down.")
