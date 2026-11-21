"""Shared WebSocket listener for externally spawned plugin Runners.

One listener accepts connections for many plugins; a per-plugin bearer
token presented during the HTTP upgrade decides which pending plugin slot
each connection claims.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from ..protocol import MAX_FRAME_BYTES
from .transport import WebSocketTransport

AuthenticateCallback = Callable[[str | None], bool]
ConnectionCallback = Callable[[WebSocketTransport, str], Awaitable[None]]


class WSPluginListener:
    """Accept and authenticate Runner WebSocket connections for the Host."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        authenticate: AuthenticateCallback,
        on_connection: ConnectionCallback,
        logger: logging.Logger | None = None,
    ) -> None:
        """Configure the listener.

        Args:
            host: Bind address.
            port: Bind port; 0 picks an ephemeral port.
            authenticate: Return True when the bearer token may connect.
            on_connection: Awaited with the accepted transport and its
                token; the connection lives until this callback returns.
            logger: Logger for listener diagnostics.
        """
        self.host = host
        self.port = port
        self.authenticate = authenticate
        self.on_connection = on_connection
        self.logger = logger or logging.getLogger("astrbot.plugin_ws_listener")
        self._server: Any = None

    async def start(self) -> None:
        """Start accepting connections."""
        import websockets

        self._server = await websockets.serve(
            self._handle,
            self.host,
            self.port,
            process_request=self._process_request,
            max_size=MAX_FRAME_BYTES + 1,
        )
        socket = self._server.sockets[0]
        self.port = socket.getsockname()[1]

    async def close(self) -> None:
        """Stop accepting connections and wait for the server to close."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _process_request(self, connection: Any, request: Any) -> Any:
        """Reject unauthenticated upgrades before the WebSocket opens."""
        if not self.authenticate(self._bearer_token(request.headers)):
            return connection.respond(401, "Unauthorized\n")
        return None

    async def _handle(self, connection: Any) -> None:
        """Run one accepted connection until its owner releases it."""
        headers = connection.request.headers if connection.request else {}
        token = self._bearer_token(headers) or ""
        transport = WebSocketTransport(connection)
        try:
            await self.on_connection(transport, token)
        finally:
            await transport.close()

    @staticmethod
    def _bearer_token(headers: Any) -> str | None:
        """Extract the bearer token from an Authorization header mapping."""
        value = headers.get("Authorization")
        if not value:
            return None
        scheme, _, token = value.partition(" ")
        token = token.strip()
        if scheme.lower() != "bearer" or not token:
            return None
        return token
