"""
Tests for AstrBot Gateway - FastAPI-based HTTP/WebSocket server.

Gateway provides:
- HTTP REST API (stats, inspector, config)
- WebSocket for real-time events
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestWebSocketManager:
    """Test suite for WebSocketManager."""

    @pytest.fixture
    def ws_manager(self):
        """Create a WebSocketManager instance."""
        from astrbot._internal.geteway.ws_manager import WebSocketManager

        return WebSocketManager()

    @pytest.fixture
    def mock_websocket(self):
        """Create a mock WebSocket."""
        ws = AsyncMock()
        ws.accept = AsyncMock()
        return ws

    @pytest.mark.asyncio
    async def test_connect_accepts_and_registers(self, ws_manager, mock_websocket):
        """connect() should accept and register the WebSocket."""
        await ws_manager.connect(mock_websocket)

        mock_websocket.accept.assert_called_once()
        assert mock_websocket in ws_manager._connections

    @pytest.mark.asyncio
    async def test_disconnect_removes_connection(self, ws_manager, mock_websocket):
        """disconnect() should remove the WebSocket from connections."""
        await ws_manager.connect(mock_websocket)
        await ws_manager.disconnect(mock_websocket)

        assert mock_websocket not in ws_manager._connections

    @pytest.mark.asyncio
    async def test_send_json_success(self, ws_manager, mock_websocket):
        """send_json() should send JSON data to WebSocket."""
        await ws_manager.connect(mock_websocket)

        data = {"type": "test", "data": {"key": "value"}}
        await ws_manager.send_json(mock_websocket, data)

        mock_websocket.send_json.assert_called_once_with(data)

    @pytest.mark.asyncio
    async def test_send_json_disconnects_on_error(self, ws_manager, mock_websocket):
        """send_json() should disconnect on error."""
        await ws_manager.connect(mock_websocket)
        mock_websocket.send_json.side_effect = Exception("Connection error")

        await ws_manager.send_json(mock_websocket, {})

        assert mock_websocket not in ws_manager._connections

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all(self, ws_manager):
        """broadcast() should send to all registered connections."""
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws2 = AsyncMock()
        ws2.accept = AsyncMock()

        await ws_manager.connect(ws1)
        await ws_manager.connect(ws2)

        data = {"type": "broadcast"}
        await ws_manager.broadcast(data)

        ws1.send_json.assert_called_once_with(data)
        ws2.send_json.assert_called_once_with(data)

    @pytest.mark.asyncio
    async def test_broadcast_removes_failed_connections(self, ws_manager):
        """broadcast() should remove connections that fail."""
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws1.send_json.side_effect = Exception("Connection error")

        ws2 = AsyncMock()
        ws2.accept = AsyncMock()

        await ws_manager.connect(ws1)
        await ws_manager.connect(ws2)

        await ws_manager.broadcast({})

        assert ws1 not in ws_manager._connections
        assert ws2 in ws_manager._connections

    @pytest.mark.asyncio
    async def test_send_to_text(self, ws_manager, mock_websocket):
        """send_to() should send text when message is string."""
        await ws_manager.connect(mock_websocket)

        await ws_manager.send_to(mock_websocket, "hello world")

        mock_websocket.send_text.assert_called_once_with("hello world")

    @pytest.mark.asyncio
    async def test_send_to_json(self, ws_manager, mock_websocket):
        """send_to() should send JSON when message is dict."""
        await ws_manager.connect(mock_websocket)

        message = {"type": "test"}
        await ws_manager.send_to(mock_websocket, message)

        mock_websocket.send_json.assert_called_once_with(message)

    def test_connection_count(self, ws_manager, mock_websocket):
        """connection_count should return number of active connections."""
        assert ws_manager.connection_count == 0

        # Note: can't use await in sync test, so just check property
        ws_manager._connections.add(mock_websocket)
        assert ws_manager.connection_count == 1


class TestAstrbotGateway:
    """Test suite for AstrbotGateway."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create a mock orchestrator."""
        orch = MagicMock()
        orch.abp = MagicMock()
        orch.abp._stars = {"test-star": MagicMock()}
        orch.lsp = MagicMock()
        orch.lsp._connected = True
        orch.mcp = MagicMock()
        orch.mcp.session = MagicMock()
        orch.acp = MagicMock()
        orch.acp._clients = []
        return orch

    @pytest.fixture
    def gateway(self, mock_orchestrator):
        """Create a gateway instance."""
        from astrbot._internal.geteway.server import AstrbotGateway

        return AstrbotGateway(mock_orchestrator)

    def test_gateway_initializes_with_orchestrator(self, gateway, mock_orchestrator):
        """Gateway should store orchestrator reference."""
        assert gateway.orchestrator is mock_orchestrator

    def test_gateway_has_websocket_manager(self, gateway):
        """Gateway should have a WebSocketManager."""
        assert hasattr(gateway, "ws_manager")
        assert gateway.ws_manager is not None

    def test_default_host_and_port(self, gateway):
        """Gateway should have default host and port."""
        assert gateway._host == "0.0.0.0"
        assert gateway._port == 8765

    def test_set_listen_address(self, gateway):
        """set_listen_address should update host and port."""
        gateway.set_listen_address("127.0.0.1", 9000)

        assert gateway._host == "127.0.0.1"
        assert gateway._port == 9000


class TestGatewayRouteHandlers:
    """Test gateway REST/WebSocket route handlers."""

    @pytest.fixture
    def gateway_with_mock_orchestrator(self):
        """Create gateway with mock orchestrator for route testing."""
        from astrbot._internal.geteway.server import AstrbotGateway

        mock_orch = MagicMock()
        mock_orch.abp = MagicMock()
        mock_orch.abp._stars = {"star-1": MagicMock(), "star-2": MagicMock()}
        mock_orch.lsp = MagicMock()
        mock_orch.lsp._connected = True
        mock_orch.mcp = MagicMock()
        mock_orch.mcp.session = MagicMock()
        mock_orch.acp = MagicMock()
        mock_orch.acp._clients = []

        return AstrbotGateway(mock_orch)

    @pytest.mark.asyncio
    async def test_list_stars(self, gateway_with_mock_orchestrator):
        """_list_stars should return list of star names."""
        result = await gateway_with_mock_orchestrator._list_stars()

        assert len(result) == 2
        star_names = [s["name"] for s in result]
        assert "star-1" in star_names
        assert "star-2" in star_names

    @pytest.mark.asyncio
    async def test_get_star_detail(self, gateway_with_mock_orchestrator):
        """_get_star_detail should return star details."""
        result = await gateway_with_mock_orchestrator._get_star_detail("star-1")

        assert result["name"] == "star-1"
        assert result["status"] == "active"

    @pytest.mark.asyncio
    async def test_get_star_detail_not_found(self, gateway_with_mock_orchestrator):
        """_get_star_detail should return error for non-existent star."""
        result = await gateway_with_mock_orchestrator._get_star_detail("non-existent")

        assert "error" in result

    @pytest.mark.asyncio
    async def test_handle_ws_message_ping(self, gateway_with_mock_orchestrator):
        """_handle_ws_message should respond to ping."""
        result = await gateway_with_mock_orchestrator._handle_ws_message(
            {"type": "ping", "data": {}}
        )

        assert result == {"type": "pong", "data": {}}

    @pytest.mark.asyncio
    async def test_handle_ws_message_unknown_type(self, gateway_with_mock_orchestrator):
        """_handle_ws_message should return error for unknown type."""
        result = await gateway_with_mock_orchestrator._handle_ws_message(
            {"type": "unknown", "data": {}}
        )

        assert result["type"] == "error"

    @pytest.mark.asyncio
    async def test_get_memory_info(self, gateway_with_mock_orchestrator):
        """_get_memory_info should return memory stats."""
        result = await gateway_with_mock_orchestrator._get_memory_info()

        assert "gc_objects" in result
        assert "python_memory" in result
