"""
AstrBot Gateway - FastAPI server for the dashboard backend.

Provides REST API endpoints and WebSocket connections for the frontend dashboard.
The gateway acts as the communication bridge between the dashboard and the orchestrator.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, cast

from astrbot import logger
from astrbot._internal.abc.base_astrbot_gateway import BaseAstrbotGateway
from astrbot._internal.abc.base_astrbot_orchestrator import BaseAstrbotOrchestrator
from astrbot._internal.geteway.ws_manager import WebSocketManager

if TYPE_CHECKING:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
else:
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError:
        logger.warning("FastAPI not installed, gateway unavailable.")
        FastAPI = cast(Any, None)
        WebSocket = cast(Any, None)
        WebSocketDisconnect = cast(Any, None)
        CORSMiddleware = cast(Any, None)

log = logger


class AstrbotGateway(BaseAstrbotGateway):
    """
    FastAPI-based gateway server for AstrBot.

    Handles:
    - REST API endpoints for configuration and stats
    - WebSocket connections for real-time communication
    - CORS middleware for dashboard access
    """

    def __init__(self, orchestrator: BaseAstrbotOrchestrator) -> None:
        self.orchestrator = orchestrator
        self.ws_manager = WebSocketManager()
        self._app: FastAPI | None = None
        self._host = "0.0.0.0"
        self._port = 8765

    async def serve(self) -> None:
        """
        Start the gateway server.

        Creates and runs a FastAPI application with WebSocket support.
        """
        if FastAPI is None:
            raise RuntimeError("FastAPI is not installed")

        log.info(f"Starting AstrBot Gateway on {self._host}:{self._port}")

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Startup
            log.info("Gateway server started.")
            yield
            # Shutdown
            await self.ws_manager.broadcast({"type": "server_shutdown"})
            log.info("Gateway server stopped.")

        self._app = FastAPI(
            title="AstrBot Gateway",
            description="Backend API for AstrBot dashboard",
            version="1.0.0",
            lifespan=lifespan,
        )

        # CORS middleware
        self._app.add_middleware(
            cast(Any, CORSMiddleware),
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Include routers
        self._setup_routes()

        # Run with uvicorn
        import uvicorn

        config = uvicorn.Config(
            self._app,
            host=self._host,
            port=self._port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        await server.serve()

    def _setup_routes(self) -> None:
        """Set up API routes."""
        if self._app is None:
            return

        from fastapi import APIRouter

        # Health check
        @self._app.get("/health")
        async def health():
            return {"status": "ok"}

        # WebSocket endpoint
        @self._app.websocket("/ws")
        async def websocket_endpoint(ws: WebSocket):
            await self.ws_manager.connect(ws)
            try:
                while True:
                    data = await ws.receive_text()
                    try:
                        message = json.loads(data)
                        response = await self._handle_ws_message(message)
                        if response:
                            await ws.send_json(response)
                    except json.JSONDecodeError:
                        await ws.send_json({"error": "Invalid JSON"})
            except WebSocketDisconnect:
                self.ws_manager.disconnect(ws)

        # Stats router
        stats_router = APIRouter(prefix="/api/stats", tags=["stats"])

        @stats_router.get("/overview")
        async def get_overview():
            return await self._get_stats_overview()

        self._app.include_router(stats_router)

        # Inspector router
        inspector_router = APIRouter(prefix="/api/inspector", tags=["inspector"])

        @inspector_router.get("/stars")
        async def list_stars():
            return await self._list_stars()

        @inspector_router.get("/stars/{star_name}")
        async def get_star(star_name: str):
            return await self._get_star_detail(star_name)

        self._app.include_router(inspector_router)

        # Memory router
        memory_router = APIRouter(prefix="/api/memory", tags=["memory"])

        @memory_router.get("/")
        async def get_memory():
            return await self._get_memory_info()

        self._app.include_router(memory_router)

    async def _handle_ws_message(
        self, message: dict[str, Any]
    ) -> dict[str, Any] | None:
        """
        Handle an incoming WebSocket message.

        Args:
            message: Parsed JSON message from the client

        Returns:
            Response message to send back, or None for no response
        """
        msg_type = message.get("type")
        data = message.get("data", {})

        if msg_type == "ping":
            return {"type": "pong", "data": {}}

        if msg_type == "call_tool":
            return await self._handle_call_tool(data)

        if msg_type == "get_stars":
            return {"type": "stars_list", "data": await self._list_stars()}

        return {
            "type": "error",
            "data": {"message": f"Unknown message type: {msg_type}"},
        }

    async def _handle_call_tool(self, data: dict[str, Any]) -> dict[str, Any]:
        """Handle a tool call request via WebSocket."""
        star_name = data.get("star")
        tool_name = data.get("tool")
        arguments = data.get("arguments", {})

        if not star_name or not tool_name:
            return {
                "type": "tool_result",
                "data": {"error": "Missing star or tool name"},
            }

        try:
            result = await self.orchestrator.abp.call_star_tool(
                star_name, tool_name, arguments
            )
            return {"type": "tool_result", "data": {"result": result}}
        except Exception as e:
            return {"type": "tool_result", "data": {"error": str(e)}}

    async def _get_stats_overview(self) -> dict[str, Any]:
        """Get overview statistics."""
        return {
            "stars_count": len(self.orchestrator.abp._stars),
            "lsp_connected": self.orchestrator.lsp._connected,
            "mcp_sessions": getattr(self.orchestrator.mcp, "session", None) is not None,
            "acp_clients": len(getattr(self.orchestrator.acp, "_clients", [])),
        }

    async def _list_stars(self) -> list[dict[str, Any]]:
        """List all registered stars."""
        stars = []
        for name in self.orchestrator.abp._stars:
            stars.append({"name": name, "status": "active"})
        return stars

    async def _get_star_detail(self, star_name: str) -> dict[str, Any]:
        """Get details of a specific star."""
        star = self.orchestrator.abp._stars.get(star_name)
        if not star:
            return {"error": f"Star '{star_name}' not found"}
        return {"name": star_name, "status": "active"}

    async def _get_memory_info(self) -> dict[str, Any]:
        """Get memory usage information."""
        import gc

        gc.collect()
        return {
            "gc_objects": len(gc.get_objects()),
            "python_memory": "N/A",  # Would need psutil for actual values
        }

    def set_listen_address(self, host: str, port: int) -> None:
        """Set the listen address for the gateway server."""
        self._host = host
        self._port = port
