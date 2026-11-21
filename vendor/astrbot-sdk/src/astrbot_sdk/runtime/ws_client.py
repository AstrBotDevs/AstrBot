"""WebSocket Host client: control a Runner that dialed into the listener.

The Runner lifecycle belongs to the operator, not the Host: start()
attaches to an already-accepted connection, close() ends the protocol
session, and wait_exited() resolves when the socket closes.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ..capabilities import DEFAULT_CAPABILITY_IDS, CapabilityGrant, CapabilitySet
from ..errors import HostUnavailable
from .stdio_client import StdioPluginClient
from .transport import FrameTransport, WebSocketTransport


class WSPluginClient(StdioPluginClient):
    """Host-side client for one externally spawned WebSocket Runner."""

    def __init__(self, transport: WebSocketTransport, **kwargs: Any) -> None:
        """Bind the client to one accepted WebSocket connection.

        Args:
            transport: Accepted connection wrapped as a frame transport.
            **kwargs: Forwarded to StdioPluginClient (timeout, logger,
                capability_handler, legacy, start_timeout).
        """
        super().__init__(None, **kwargs)
        self._transport: FrameTransport | None = transport

    def _compute_grants(
        self,
        granted_capabilities: CapabilitySet | None,
    ) -> CapabilitySet:
        # External runners have no local metadata to intersect with: the
        # listener configuration declares the effective grants host-side,
        # and the runner-level defaults (KV storage, asset transfer) are
        # auto-granted like they are for local runners.
        requested = granted_capabilities or CapabilitySet()
        requested_ids = {grant.id for grant in requested.values()}
        return CapabilitySet(
            list(requested.values())
            + [
                CapabilityGrant(id=capability_id)
                for capability_id in sorted(DEFAULT_CAPABILITY_IDS - requested_ids)
            ]
        )

    async def _open_transport(self) -> FrameTransport:
        """Attach to the pre-accepted connection."""
        transport = self._transport
        if transport is None:
            raise HostUnavailable("websocket plugin Runner is not attached")
        return transport

    async def _close_transport(self) -> None:
        """Close the WebSocket connection."""
        transport = self._transport
        if transport is not None:
            await transport.close()

    @property
    def is_running(self) -> bool:
        """Whether the WebSocket connection is open."""
        transport = self._transport
        return transport is not None and not transport.closed

    async def wait_exited(self) -> int | None:
        """Wait for the connection to close; there is no exit code."""
        transport = self._transport
        if transport is not None:
            await transport.wait_closed()
        return None

    def kill_process(self) -> None:
        """Close the connection; the Runner process is not ours to kill."""
        transport = self._transport
        if transport is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(transport.close())
