"""
AstrBot Gateway - HTTP/WebSocket API server.

Built on FastAPI, provides:
- HTTP REST API (stats, inspector, config)
- WebSocket for real-time events
- Static file serving (dashboard)
- Authentication (JWT/API key)
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseAstrbotGateway(ABC):
    """
    Gateway: HTTP/WebSocket server built on FastAPI.

    ┌─────────────────────────────────────────────────────────┐
    │                      FastAPI App                        │
    ├─────────────────────────────────────────────────────────┤
    │  REST Endpoints              WebSocket                  │
    │  ├─ GET /api/stats          ├─ /ws (connection manager)│
    │  ├─ GET /api/inspector/*   │                          │
    │  ├─ GET /api/memory/*      │                          │
    │  └─ ...                    │                          │
    │                                                         │
    │  Middleware: CORS, Auth, Logging                        │
    └─────────────────────────────────────────────────────────┘
                          │
                          ▼
              ┌─────────────────────────┐
              │     Orchestrator        │
              │  (owns protocol clients)│
              └─────────────────────────┘

    Routes (typical):
        GET  /              → Dashboard static files
        GET  /api/stats     → System statistics
        GET  /api/inspector/stars → List registered stars
        WS   /ws            → WebSocket for real-time events

    serve() Lifecycle:
        1. Create FastAPI app
        2. Register routes
        3. Start WebSocket manager
        4. Bind to host:port
        5. Run ASGI server (uvicorn/hypercorn)
        6. Block until shutdown
        7. Close all connections

    Subclass must implement:
    - serve(): start server, block until shutdown
    """

    @abstractmethod
    async def serve(self) -> None:
        """
        Start gateway server - blocks until shutdown.

        Should:
        1. Create FastAPI app with routes
        2. Configure CORS, auth middleware
        3. Start WebSocket connection manager
        4. Bind to ASTRBOT_PORT (default 6185)
        5. Run ASGI server
        6. Handle graceful shutdown on SIGTERM/SIGINT

        Raises:
            OSError: address already in use
        """
        ...
