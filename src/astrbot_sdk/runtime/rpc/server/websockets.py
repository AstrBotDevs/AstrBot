from __future__ import annotations

import asyncio
import json

import aiohttp
from aiohttp import web
from loguru import logger

from ..jsonrpc import (
    JSONRPCErrorResponse,
    JSONRPCMessage,
    JSONRPCRequest,
    JSONRPCSuccessResponse,
)
from .base import JSONRPCServer


class WebSocketServer(JSONRPCServer):
    """JSON-RPC server using WebSocket for communication.

    This runs in the plugin process and accepts connections from AstrBot via WebSocket.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,  # 0 means auto-assign
        path: str = "/",
        heartbeat: float = 30.0,
    ) -> None:
        """Initialize the WebSocket server.

        Args:
            host: Host to bind to
            port: Port to bind to (0 for auto-assign)
            path: WebSocket endpoint path
            heartbeat: Heartbeat interval in seconds (0 to disable)
        """
        super().__init__()
        self._host = host
        self._port = port
        self._path = path
        self._heartbeat = heartbeat
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._ws: web.WebSocketResponse | None = None
        self._write_lock = asyncio.Lock()
        self._actual_port: int | None = None

    async def start(self) -> None:
        """Start the WebSocket server and begin listening for connections."""
        if self._running:
            logger.warning("WebSocketServer is already running")
            return

        self._running = True
        self._app = web.Application()
        self._app.router.add_get(self._path, self._handle_websocket)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()

        # Get the actual port (useful when port=0)
        if self._site._server and hasattr(self._site._server, "sockets"):
            sockets = getattr(self._site._server, "sockets", None)
            if sockets:
                for socket in sockets:
                    self._actual_port = socket.getsockname()[1]
                    break

        logger.info(
            f"WebSocketServer started on ws://{self._host}:{self._actual_port or self._port}{self._path}"
        )

    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Handle incoming WebSocket connections.

        Args:
            request: The aiohttp request object

        Returns:
            WebSocket response
        """
        ws = web.WebSocketResponse(
            heartbeat=self._heartbeat if self._heartbeat > 0 else None
        )
        await ws.prepare(request)

        # Only allow one connection at a time (typical for plugin IPC)
        if self._ws and not self._ws.closed:
            logger.warning(
                "Rejecting new connection - already have an active connection"
            )
            await ws.close(
                code=1008, message=b"Server already has an active connection"
            )
            return ws

        self._ws = ws
        logger.info(f"WebSocket connection established from {request.remote}")

        try:
            await self._message_loop(ws)
        except Exception as e:
            logger.error(f"Error in WebSocket message loop: {e}")
        finally:
            if self._ws == ws:
                self._ws = None
            logger.info("WebSocket connection closed")

        return ws

    async def _message_loop(self, ws: web.WebSocketResponse) -> None:
        """Main loop to receive messages from WebSocket.

        Args:
            ws: The WebSocket response object
        """
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    message = self._parse_message(msg.data)
                    await self._handle_message(message)
                except Exception as e:
                    logger.error(f"Failed to parse message: {e}, raw data: {msg.data}")

            elif msg.type == aiohttp.WSMsgType.BINARY:
                try:
                    text = msg.data.decode("utf-8")
                    message = self._parse_message(text)
                    await self._handle_message(message)
                except Exception as e:
                    logger.error(f"Failed to parse binary message: {e}")

            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"WebSocket error: {ws.exception()}")
                break

            elif msg.type in (
                aiohttp.WSMsgType.CLOSE,
                aiohttp.WSMsgType.CLOSING,
                aiohttp.WSMsgType.CLOSED,
            ):
                logger.debug("WebSocket closing")
                break

    async def stop(self) -> None:
        """Stop the WebSocket server and cleanup resources."""
        if not self._running:
            return

        self._running = False

        # Close active WebSocket connection
        if self._ws and not self._ws.closed:
            await self._ws.close()
            self._ws = None

        # Cleanup server
        if self._site:
            await self._site.stop()
            self._site = None

        if self._runner:
            await self._runner.cleanup()
            self._runner = None

        self._app = None
        logger.info("WebSocketServer stopped")

    async def send_message(self, message: JSONRPCMessage) -> None:
        """Send a JSON-RPC message through the WebSocket.

        Args:
            message: The JSON-RPC message to send

        Raises:
            RuntimeError: If no WebSocket connection is active
        """
        if not self._ws or self._ws.closed:
            raise RuntimeError("No active WebSocket connection")

        async with self._write_lock:
            try:
                json_str = message.model_dump_json(exclude_none=True)
                await self._ws.send_str(json_str)
            except Exception as e:
                logger.error(f"Failed to send message: {e}")
                raise

    @property
    def port(self) -> int | None:
        """Get the actual port the server is listening on.

        Returns:
            Port number, or None if server is not started
        """
        return self._actual_port or self._port

    @property
    def url(self) -> str | None:
        """Get the WebSocket URL the server is listening on.

        Returns:
            WebSocket URL, or None if server is not started
        """
        if self._actual_port or self._port:
            port = self._actual_port or self._port
            return f"ws://{self._host}:{port}{self._path}"
        return None

    def _parse_message(self, data: str) -> JSONRPCMessage:
        """Parse a JSON-RPC message from a string.

        Args:
            data: JSON string to parse

        Returns:
            Parsed JSONRPCMessage (Request, SuccessResponse, or ErrorResponse)
        """
        obj = json.loads(data)

        # Determine message type based on presence of fields
        if "method" in obj:
            return JSONRPCRequest.model_validate(obj)
        elif "error" in obj:
            return JSONRPCErrorResponse.model_validate(obj)
        elif "result" in obj:
            return JSONRPCSuccessResponse.model_validate(obj)
        else:
            raise ValueError(f"Invalid JSON-RPC message: {obj}")
