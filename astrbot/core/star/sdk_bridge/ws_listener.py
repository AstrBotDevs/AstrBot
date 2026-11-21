"""Shared WebSocket listener for externally spawned plugin Runners.

Local plugins are spawned by the Host and talk over stdio. External
plugins (another machine, a container, a future non-Python SDK) dial out
to this listener instead; a per-plugin bearer token presented during the
HTTP upgrade claims the connection for its configured plugin slot.
"""

from __future__ import annotations

import asyncio
import logging

from astrbot_sdk.runtime.transport import WebSocketTransport
from astrbot_sdk.runtime.ws_listener import WSPluginListener

logger = logging.getLogger("astrbot.sdk_bridge.ws")


class ExternalRunnerListener:
    """Accept external Runner connections and route them by bearer token."""

    def __init__(self, host: str, port: int) -> None:
        """Configure the listener for one bind address."""
        self.host = host
        self.port = port
        self._claims: dict[str, asyncio.Queue[WebSocketTransport]] = {}
        self._listener = WSPluginListener(
            host,
            port,
            authenticate=self._authenticate,
            on_connection=self._on_connection,
            logger=logger,
        )
        self._started = False

    async def start(self) -> None:
        """Bind the socket; idempotent."""
        if self._started:
            return
        await self._listener.start()
        self.port = self._listener.port
        self._started = True
        logger.info(f"SDK bridge external listener on {self.host}:{self.port}")

    async def stop(self) -> None:
        """Close the listener and drop every pending claim."""
        self._claims.clear()
        await self._listener.close()
        self._started = False

    def register(self, token: str) -> asyncio.Queue[WebSocketTransport]:
        """Register one plugin slot and return its connection claim queue.

        Raises:
            ValueError: Another slot already uses this token.
        """
        if token in self._claims:
            raise ValueError("duplicate external runner token")
        queue: asyncio.Queue[WebSocketTransport] = asyncio.Queue()
        self._claims[token] = queue
        return queue

    def unregister(self, token: str) -> None:
        """Release one plugin slot; new connections with its token get 401."""
        self._claims.pop(token, None)

    def _authenticate(self, token: str | None) -> bool:
        return token is not None and token in self._claims

    async def _on_connection(
        self,
        transport: WebSocketTransport,
        token: str,
    ) -> None:
        queue = self._claims.get(token)
        if queue is None:
            # The slot was unregistered between upgrade and handler start.
            return
        await queue.put(transport)
        await transport.wait_closed()
