"""
ABP (AstrBot Protocol) client implementation.

ABP is the built-in plugin protocol where the orchestrator acts as client
connecting to internal stars (plugins) embedded in the runtime.
"""

from __future__ import annotations

from typing import Any

from astrbot import logger
from astrbot._internal.abc.abp.base_astrbot_abp_client import BaseAstrbotAbpClient

log = logger


class AstrbotAbpClient(BaseAstrbotAbpClient):
    """
    ABP client for communicating with internal stars (built-in plugins).

    The orchestrator acts as the client, sending requests to and receiving
    notifications from stars running within the same process.
    """

    def __init__(self) -> None:
        self._connected = False
        self._stars: dict[str, Any] = {}
        # Use a simple dict for pending requests; we avoid asyncio.Future here.
        self._pending_requests: dict[str, Any] = {}
        self._request_id = 0

    @property
    def connected(self) -> bool:
        """True if connected to stars registry."""
        return self._connected

    async def connect(self) -> None:
        """Connect to internal stars registry."""
        log.debug("ABP client connecting to internal stars...")
        self._connected = True
        log.info("ABP client connected to internal stars registry.")

    async def call_star_tool(
        self, star_name: str, tool_name: str, arguments: dict[str, Any]
    ) -> Any:
        """
        Call a tool on a registered star.

        Args:
            star_name: Name of the star (plugin)
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool call result
        """
        if not self._connected:
            raise RuntimeError("ABP client is not connected")

        star = self._stars.get(star_name)
        if not star:
            raise ValueError(f"Star '{star_name}' not found")

        request_id = f"{self._request_id}"
        self._request_id += 1

        # No asyncio.Future used; store a placeholder entry for tracking if needed.
        self._pending_requests[request_id] = None

        try:
            # Call the star's tool handler
            result = await star.call_tool(tool_name, arguments)
            return result
        finally:
            self._pending_requests.pop(request_id, None)

    def register_star(self, star_name: str, star_instance: Any) -> None:
        """Register a star (plugin) with the ABP client."""
        self._stars[star_name] = star_instance
        log.debug(f"Star '{star_name}' registered with ABP client.")

    def unregister_star(self, star_name: str) -> None:
        """Unregister a star from the ABP client."""
        self._stars.pop(star_name, None)
        log.debug(f"Star '{star_name}' unregistered from ABP client.")

    async def shutdown(self) -> None:
        """Shutdown the ABP client connection."""
        self._connected = False
        # Clear any pending requests (no asyncio futures used in this implementation)
        self._pending_requests.clear()
        log.info("ABP client shut down.")
