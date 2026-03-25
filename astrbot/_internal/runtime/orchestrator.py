"""
AstrBot Orchestrator - core runtime that coordinates all protocol clients.

The orchestrator manages the lifecycle of LSP, MCP, ACP, and ABP clients,
and runs the main event loop that dispatches messages between components.
"""

from __future__ import annotations

from typing import Any

import anyio

from astrbot import logger
from astrbot._internal.abc.base_astrbot_orchestrator import BaseAstrbotOrchestrator
from astrbot._internal.protocols.abp.client import AstrbotAbpClient
from astrbot._internal.protocols.acp.client import AstrbotAcpClient
from astrbot._internal.protocols.lsp.client import AstrbotLspClient
from astrbot._internal.protocols.mcp.client import McpClient
from astrbot._internal.stars import RuntimeStatusStar

log = logger


class AstrbotOrchestrator(BaseAstrbotOrchestrator):
    """
    Core runtime orchestrator for AstrBot.

    Manages:
    - LSP client: Language Server Protocol for editor integrations
    - MCP client: Model Context Protocol for external tool servers
    - ACP client: AstrBot Communication Protocol for inter-service communication
    - ABP client: AstrBot Protocol for built-in star (plugin) communication
    """

    def __init__(self) -> None:
        # Initialize protocol clients (use concrete types for full method access)
        self.lsp = AstrbotLspClient()
        self.mcp = McpClient()
        self.acp = AstrbotAcpClient()
        self.abp = AstrbotAbpClient()

        self._running = False
        self._stars: dict[str, Any] = {}
        self._message_count: int = 0
        self._last_activity_timestamp: float | None = None

        # Auto-register RuntimeStatusStar
        self._runtime_status_star = RuntimeStatusStar()
        self._runtime_status_star.set_orchestrator(self)
        self._stars["runtime-status-star"] = self._runtime_status_star
        self.abp.register_star("runtime-status-star", self._runtime_status_star)

        log.debug("AstrbotOrchestrator initialized.")

    async def start(self) -> None:
        """
        Initialize all protocol clients.

        Calls connect() on all protocol clients to prepare them for use.
        """
        log.info("Starting AstrbotOrchestrator...")

        await self.lsp.connect()
        await self.mcp.connect()
        await self.acp.connect()
        await self.abp.connect()

        self._running = True
        log.info("AstrbotOrchestrator started.")

    async def run_loop(self) -> None:
        """
        Main orchestrator event loop.

        This loop runs continuously, handling:
        - Periodic health checks of protocol clients
        - Message routing between protocols
        - Star (plugin) lifecycle management
        """
        self._running = True
        log.info("AstrbotOrchestrator run loop started.")

        stop_event = anyio.Event()

        def set_stop() -> None:
            stop_event.set()

        # Store the callback for cleanup
        self._stop_callback = set_stop

        try:
            while self._running:
                # TODO: Periodic tasks:
                # - Check LSP server health
                # - Check MCP session status
                # - Check ACP client connections
                # - Process any pending star notifications

                # Wait for 5 seconds or until shutdown is called
                with anyio.move_on_after(5):
                    await stop_event.wait()

        except anyio.get_cancelled_exc_class():
            log.info("Orchestrator run loop cancelled.")
        finally:
            self._running = False
            self._stop_callback = None
            log.info("AstrbotOrchestrator run loop stopped.")

    async def register_star(self, name: str, star_instance: Any) -> None:
        """
        Register a star (plugin) with the orchestrator.

        Args:
            name: Unique name for the star
            star_instance: Star plugin instance
        """
        self._stars[name] = star_instance
        self.abp.register_star(name, star_instance)
        log.info(f"Star '{name}' registered.")

    async def unregister_star(self, name: str) -> None:
        """
        Unregister a star (plugin) from the orchestrator.

        Args:
            name: Name of the star to unregister
        """
        self._stars.pop(name, None)
        self.abp.unregister_star(name)
        log.info(f"Star '{name}' unregistered.")

    async def get_star(self, name: str) -> Any | None:
        """Get a registered star by name."""
        return self._stars.get(name)

    async def list_stars(self) -> list[str]:
        """List all registered star names."""
        return list(self._stars.keys())

    def record_activity(self) -> None:
        """Record a message activity for stats tracking."""
        self._message_count += 1
        import time

        self._last_activity_timestamp = time.time()

    async def shutdown(self) -> None:
        """
        Shutdown the orchestrator and all protocol clients.
        """
        log.info("Shutting down AstrbotOrchestrator...")
        self._running = False

        # Shutdown all protocol clients
        await self.lsp.shutdown()
        await self.acp.shutdown()
        await self.abp.shutdown()

        # MCP cleanup
        await self.mcp.cleanup()

        log.info("AstrbotOrchestrator shut down.")
