"""
WebSocket connection manager for the AstrBot gateway.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import anyio

from astrbot import logger

if TYPE_CHECKING:
    from fastapi import WebSocket
else:
    try:
        from fastapi import WebSocket
    except ImportError:
        logger.warning("FastAPI not installed, WebSocketManager unavailable.")
        WebSocket = cast(Any, None)

log = logger


class WebSocketManager:
    """
    Manages all active WebSocket connections.

    Provides connection/disconnection handling and broadcast capabilities.
    """

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = anyio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        log.debug(f"WebSocket connected. Total: {len(self._connections)}")

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            self._connections.discard(websocket)
        log.debug(f"WebSocket disconnected. Total: {len(self._connections)}")

    async def send_json(self, websocket: WebSocket, data: dict[str, Any]) -> None:
        """
        Send JSON data to a specific WebSocket.

        Args:
            websocket: Target WebSocket connection
            data: Data to send (must be JSON-serializable)
        """
        try:
            await websocket.send_json(data)
        except Exception as e:
            log.warning(f"Failed to send to WebSocket: {e}")
            await self.disconnect(websocket)

    async def broadcast(self, data: dict[str, Any]) -> None:
        """
        Broadcast JSON data to all connected WebSockets.

        Args:
            data: Data to broadcast (must be JSON-serializable)
        """
        async with self._lock:
            connections = list(self._connections)

        for conn in connections:
            try:
                await conn.send_json(data)
            except Exception as e:
                log.warning(f"Failed to broadcast to WebSocket: {e}")
                async with self._lock:
                    self._connections.discard(conn)

    async def send_to(self, websocket: WebSocket, message: str | dict[str, Any]) -> None:
        """
        Send a message to a specific WebSocket.

        Args:
            websocket: Target WebSocket connection
            message: Message to send (string or dict)
        """
        try:
            if isinstance(message, str):
                await websocket.send_text(message)
            else:
                await websocket.send_json(message)
        except Exception as e:
            log.warning(f"Failed to send to WebSocket: {e}")
            await self.disconnect(websocket)

    @property
    def connection_count(self) -> int:
        """Return the number of active connections."""
        return len(self._connections)
