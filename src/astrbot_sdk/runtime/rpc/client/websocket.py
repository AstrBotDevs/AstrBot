from __future__ import annotations

import asyncio
import json

import aiohttp
from loguru import logger

from ..jsonrpc import (
    JSONRPCErrorResponse,
    JSONRPCMessage,
    JSONRPCRequest,
    JSONRPCSuccessResponse,
)
from .base import JSONRPCClient


class WebSocketClient(JSONRPCClient):
    """JSON-RPC client using WebSocket for communication."""

    def __init__(
        self,
        url: str,
        heartbeat: float = 30.0,
        auto_reconnect: bool = True,
        reconnect_interval: float = 5.0,
    ) -> None:
        """Initialize the WebSocket client.

        Args:
            url: WebSocket server URL (e.g., ws://127.0.0.1:8765/rpc)
            heartbeat: Heartbeat interval in seconds (0 to disable)
            auto_reconnect: Whether to automatically reconnect on disconnection
            reconnect_interval: Interval between reconnection attempts in seconds
        """
        super().__init__()
        self._url = url
        self._heartbeat = heartbeat
        self._auto_reconnect = auto_reconnect
        self._reconnect_interval = reconnect_interval
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._write_lock = asyncio.Lock()
        self._read_task: asyncio.Task | None = None
        self._reconnect_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Connect to the WebSocket server."""
        if self._running:
            logger.warning("WebSocketClient is already running")
            return

        self._running = True
        self._session = aiohttp.ClientSession()

        await self._connect()
        logger.info(f"WebSocketClient started and connected to {self._url}")

    async def _connect(self) -> None:
        """Establish WebSocket connection to the server."""
        try:
            if not self._session:
                raise RuntimeError("Session not initialized")

            self._ws = await self._session.ws_connect(
                self._url,
                heartbeat=self._heartbeat if self._heartbeat > 0 else None,
            )
            logger.info(f"Connected to WebSocket server: {self._url}")

            # Start reading messages
            self._read_task = asyncio.create_task(self._read_loop())

        except Exception as e:
            logger.error(f"Failed to connect to WebSocket server: {e}")
            if self._auto_reconnect and self._running:
                logger.info(
                    f"Will retry connection in {self._reconnect_interval} seconds..."
                )
                await asyncio.sleep(self._reconnect_interval)
                if self._running:
                    await self._connect()
            else:
                raise

    async def stop(self) -> None:
        """Disconnect from the WebSocket server and cleanup resources."""
        if not self._running:
            return

        self._running = False

        # Cancel reconnection task if running
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None

        # Cancel read task
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
            self._read_task = None

        # Close WebSocket connection
        if self._ws and not self._ws.closed:
            await self._ws.close()
            self._ws = None

        # Close session
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

        logger.info("WebSocketClient stopped")

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

    async def _read_loop(self) -> None:
        """Main loop to read messages from WebSocket."""
        if not self._ws:
            logger.error("WebSocket connection not established")
            return

        logger.debug("Started reading from WebSocket")

        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        message = self._parse_message(msg.data)
                        await self._handle_message(message)
                    except Exception as e:
                        logger.error(
                            f"Failed to parse message: {e}, raw data: {msg.data}"
                        )

                elif msg.type == aiohttp.WSMsgType.BINARY:
                    try:
                        text = msg.data.decode("utf-8")
                        message = self._parse_message(text)
                        await self._handle_message(message)
                    except Exception as e:
                        logger.error(f"Failed to parse binary message: {e}")

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    if self._ws:
                        logger.error(f"WebSocket error: {self._ws.exception()}")
                    break

                elif msg.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSING,
                    aiohttp.WSMsgType.CLOSED,
                ):
                    logger.debug("WebSocket closing")
                    break

        except asyncio.CancelledError:
            logger.debug("Read loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in read loop: {e}")
        finally:
            logger.debug("Stopped reading from WebSocket")

            # Handle reconnection
            if self._running and self._auto_reconnect:
                logger.info("Connection lost, attempting to reconnect...")
                self._reconnect_task = asyncio.create_task(self._reconnect())

    async def _reconnect(self) -> None:
        """Attempt to reconnect to the WebSocket server."""
        while self._running and self._auto_reconnect:
            try:
                logger.info(
                    f"Reconnecting to {self._url} in {self._reconnect_interval} seconds..."
                )
                await asyncio.sleep(self._reconnect_interval)

                if not self._running:
                    break

                await self._connect()
                logger.info("Reconnected successfully")
                break

            except Exception as e:
                logger.error(f"Reconnection failed: {e}")
                # Continue loop to retry

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
