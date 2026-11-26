"""WebSocket Runner entry point: the plugin side dials out to the Host.

Used when AstrBot cannot spawn the Runner — plugins on another machine, in
a container, or written against a future non-Python SDK. The Runner
authenticates with a per-plugin bearer token during the HTTP upgrade.
"""

from __future__ import annotations

from pathlib import Path

from ..protocol import MAX_FRAME_BYTES
from .stdio_server import StdioPluginServer
from .transport import WebSocketTransport

# Environment variable carrying the per-plugin bearer token. Kept out of
# argv so it does not leak through process listings.
RUNNER_TOKEN_ENV = "ASTRBOT_RUNNER_TOKEN"


async def serve_ws_plugin(
    plugin_root: Path,
    url: str,
    *,
    token: str | None = None,
    legacy: bool = False,
) -> None:
    """Run one plugin Runner over a WebSocket connection to the Host.

    Args:
        plugin_root: Plugin repository root.
        url: Host listener URL (``ws://`` or ``wss://``).
        token: Bearer token authenticating this plugin during the upgrade.
        legacy: Load the plugin through the legacy compat layer.

    Raises:
        websockets.exceptions.InvalidStatus: The listener rejects the
            upgrade (for example a missing or wrong token yields 401).
    """
    import websockets

    headers = {"Authorization": f"Bearer {token}"} if token else None
    async with websockets.connect(
        url,
        additional_headers=headers,
        max_size=MAX_FRAME_BYTES + 1,
        # Plugin-side proxies commonly break long-lived RPC sockets; the
        # operator can still route explicitly via the URL.
        proxy=None,
    ) as connection:
        server = StdioPluginServer(
            plugin_root,
            legacy=legacy,
            transport=WebSocketTransport(connection),
        )
        await server.serve()
