"""
AstrBot Orchestrator - core runtime lifecycle manager.

Architecture
============

    ┌─────────────────────────────────────────────────────┐
    │                   Orchestrator                       │
    │  (owns lifecycle of all protocol clients + stars)  │
    └─────────────────────────────────────────────────────┘
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
    ┌─────────┐    ┌─────────┐    ┌─────────┐
    │   LSP   │    │   MCP   │    │   ACP   │
    │ Client  │    │ Client  │    │ Client  │
    └─────────┘    └─────────┘    └─────────┘
         │              │              │
         ▼              ▼              ▼
    LSP Servers    MCP Servers    ACP Services

    ┌─────────────────────────────────────────────────────┐
    │                      ABP Client                      │
    │              (in-process star registry)              │
    └─────────────────────────────────────────────────────┘
                        │
                        ▼
                   ┌─────────┐
                   │  Stars  │
                   │(Plugins) │
                   └─────────┘


Lifecycle State Machine
=======================

 States:
   ┌─────────┐
   │  INIT   │───► orchestrator created, clients not initialized
   └────┬────┘
        │ start()
        ▼
   ┌─────────┐
   │ RUNNING │◄─── run_loop() executing
   └────┬────┘
        │ shutdown()
        ▼
   ┌──────────┐
   │ SHUTDOWN │─── all clients closed, ready for GC
   └──────────┘

 Transitions:
   INIT + start() ──► RUNNING
   RUNNING + shutdown() ──► SHUTDOWN

 For each protocol client, the orchestrator:
   1. Creates instance in __init__
   2. Calls connect() to initialize
   3. Calls protocol-specific setup (connect_to_server, etc)
   4. Manages via run_loop() heartbeat
   5. Calls shutdown() on final cleanup


Star Registration Flow
=====================

   orchestrator.register_star("my-star", MyStar())
           │
           ▼
   ┌───────────────────┐
   │  ABP Client       │
   │  .register_star() │
   └───────────────────┘
           │
           ▼
   ┌───────────────────┐
   │  Internal dict    │
   │  {"my-star": obj} │
   └───────────────────┘


Message Routing (conceptual)
===========================

   External Tool Call
          │
          ▼
   ┌──────────────┐    list_tools()    ┌──────────────┐
   │  MCP Client  │────────────────────►│  MCP Server  │
   └──────────────┘◄────────────────────└──────────────┘
          │              tool result
          ▼
   ┌──────────────┐    call_tool()      ┌──────────────┐
   │    ABP       │────────────────────►│    Star      │
   │   Client     │◄────────────────────└──────────────┘
   └──────────────┘              tool result
          │
          ▼
   Return to caller


run_loop() Responsibilities
===========================

   while running:
       │─ check LSP server health (ping/heartbeat)
       │─ check MCP session status (reconnect if needed)
       │─ check ACP client connections
       │─ process any pending star notifications
       │─ sleep(SLEEP_INTERVAL)


Shutdown Sequence
==================

   shutdown()
       │
       ├─ set _running = False
       │
       ├─ LSP.shutdown()
       │     └─ send "shutdown" request
       │     └─ terminate subprocess
       │
       ├─ ACP.shutdown()
       │     └─ close TCP/Unix connections
       │
       ├─ ABP.shutdown()
       │     └─ cancel pending requests
       │
       └─ MCP.cleanup()
             └─ close all sessions
             └─ cleanup subprocesses


Exception Handling
==================

   Each protocol client should:
   - Catch connection errors
   - Attempt reconnection with exponential backoff
   - Log errors but don't crash run_loop
   - Raise on irrecoverable failures

   The orchestrator run_loop should:
   - Catch CancelledError on shutdown
   - Catch Exception and log (don't crash)
   - Ensure cleanup runs in finally block
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from astrbot._internal.protocols.abp.client import AstrbotAbpClient
    from astrbot._internal.protocols.acp.client import AstrbotAcpClient
    from astrbot._internal.protocols.lsp.client import AstrbotLspClient
    from astrbot._internal.protocols.mcp.client import McpClient


#: Default heartbeat interval for run_loop()
DEFAULT_SLEEP_INTERVAL: float = 5.0


class BaseAstrbotOrchestrator(ABC):
    """
    Core runtime: owns lifecycle of all protocol clients and stars.

    ┌────────────────────────────────────────────────────────────┐
    │  Protocol Clients (always present, never None after init) │
    ├────────────────────────────────────────────────────────────┤
    │  lsp: Language Server Protocol                            │
    │       Purpose: code completion, diagnostics, hover, etc   │
    │       Transport: stdio subprocess                         │
    │                                                            │
    │  mcp: Model Context Protocol                              │
    │       Purpose: external tool access                       │
    │       Transport: stdio | SSE | HTTP                       │
    │                                                            │
    │  acp: AstrBot Communication Protocol                      │
    │       Purpose: inter-service communication                  │
    │       Transport: TCP | Unix Socket                         │
    │                                                            │
    │  abp: AstrBot Protocol                                    │
    │       Purpose: in-process star (plugin) communication      │
    │       Transport: direct method calls                      │
    └────────────────────────────────────────────────────────────┘

    ┌────────────────────────────────────────────────────────────┐
    │  Star Registry                                            │
    ├────────────────────────────────────────────────────────────┤
    │  _stars: dict[str, Any]                                   │
    │  Stars are plugins registered by name                     │
    │  ABP client delegates calls to registered stars           │
    └────────────────────────────────────────────────────────────┘

    Subclass must implement:
    - __init__(): create all protocol client instances
    - run_loop(): main event loop (block until shutdown)
    - register_star(name, instance): add to registry + ABP
    - unregister_star(name): remove from registry + ABP
    - shutdown(): clean up all clients
    """

    #: LSP client for language intelligence
    lsp: AstrbotLspClient

    #: MCP client for external tools
    mcp: McpClient

    #: ACP client for inter-service communication
    acp: AstrbotAcpClient

    #: ABP client for in-process star communication
    abp: AstrbotAbpClient

    def __init__(self) -> None:
        """
        Initialize orchestrator and all protocol clients.

        After __init__, all clients exist but are not connected.
        Call start() or run_loop() to begin operation.

        Example:
            class MyOrchestrator(BaseAstrbotOrchestrator):
                def __init__(self):
                    self.lsp = AstrbotLspClient()
                    self.mcp = McpClient()
                    self.acp = AstrbotAcpClient()
                    self.abp = AstrbotAbpClient()
                    self._stars: dict[str, Any] = {}
                    self._running = False
        """
        self._stars: dict[str, Any] = {}
        self._running: bool = False

    @property
    def running(self) -> bool:
        """True if run_loop() is executing."""
        return self._running

    @abstractmethod
    async def start(self) -> None:
        """
        Initialize all protocol clients.

        Called once before run_loop(). Should:
        1. Call lsp.connect()
        2. Call mcp.connect()
        3. Call acp.connect()
        4. Call abp.connect()
        5. Set _running = True

        Raises:
            Exception: if any client fails to initialize
        """
        ...

    @abstractmethod
    async def run_loop(self) -> None:
        """
        Main event loop - blocks until shutdown.

        Execution:
            self._running = True
            try:
                while self._running:
                    await self._heartbeat()
                    await anyio.sleep(DEFAULT_SLEEP_INTERVAL)
            except asyncio.CancelledError:
                pass  # shutdown requested
            finally:
                self._running = False

        _heartbeat() responsibilities:
        - Check LSP server health (optional ping)
        - Check MCP session status, reconnect if needed
        - Check ACP connections
        - Process any pending star notifications

        Raises:
            asyncio.CancelledError: when shutdown() called

        Note:
            Subclass defines _heartbeat() for periodic tasks.
            This method only handles the loop control.
        """
        ...

    @abstractmethod
    async def register_star(self, name: str, star_instance: Any) -> None:
        """
        Register a star (plugin) with the orchestrator.

        Args:
            name: Unique identifier for the star
            instance: Star plugin instance (must have .call_tool() method)

        Does:
            self._stars[name] = star_instance
            self.abp.register_star(name, star_instance)

        Raises:
            ValueError: if name already registered
        """
        ...

    @abstractmethod
    async def unregister_star(self, name: str) -> None:
        """
        Unregister a star (plugin) from the orchestrator.

        Args:
            name: Identifier of star to remove

        Does:
            del self._stars[name]
            self.abp.unregister_star(name)

        Note:
            Idempotent - does nothing if name not found.
        """
        ...

    @abstractmethod
    async def get_star(self, name: str) -> Any | None:
        """Get registered star by name. Returns None if not found."""
        ...

    @abstractmethod
    async def list_stars(self) -> list[str]:
        """Return list of registered star names."""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """
        Graceful shutdown of orchestrator and all clients.

        Execution order:
            1. self._running = False  (stop run_loop)
            2. await lsp.shutdown()
            3. await acp.shutdown()
            4. await abp.shutdown()
            5. await mcp.cleanup()

        Does NOT unregister stars - caller should do that first.

        After shutdown, orchestrator is ready for garbage collection.
        """
        ...
