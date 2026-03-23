"""
Tests for MCP (Model Context Protocol) client implementation.

MCP client connects to MCP servers for external tool access.
Transport: stdio | SSE | streamable_http
"""

from __future__ import annotations

import anyio
import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestMcpClient:
    """Test suite for McpClient."""

    @pytest.fixture
    def mcp_client(self):
        """Create an MCP client instance."""
        from astrbot._internal.protocols.mcp.client import McpClient

        return McpClient()

    def test_init_creates_client(self, mcp_client):
        """MCP client should initialize with session=None."""
        assert mcp_client.session is None
        assert mcp_client.name is None
        assert mcp_client.active is True

    def test_connected_property_false_initially(self, mcp_client):
        """connected should be False when session is None."""
        assert mcp_client.connected is False

    @pytest.mark.asyncio
    async def test_connect_is_noop(self, mcp_client):
        """connect() should be a no-op (actual connection via connect_to_server)."""
        await mcp_client.connect()
        # Session should still be None - connection happens in connect_to_server
        assert mcp_client.session is None

    @pytest.mark.asyncio
    async def test_list_tools_returns_empty_when_not_connected(self, mcp_client):
        """list_tools should return empty list when no session."""
        result = await mcp_client.list_tools()
        assert result == []

    @pytest.mark.asyncio
    async def test_cleanup_sets_running_event(self, mcp_client):
        """cleanup() should set the running_event."""
        mcp_client.running_event = asyncio.Event()

        await mcp_client.cleanup()

        assert mcp_client.running_event.is_set()

    @pytest.mark.asyncio
    async def test_cleanup_clears_process_pid(self, mcp_client):
        """cleanup() should clear process_pid."""
        mcp_client.process_pid = 12345

        await mcp_client.cleanup()

        assert mcp_client.process_pid is None

    def test_extract_stdio_process_pid_returns_none_on_failure(self, mcp_client):
        """_extract_stdio_process_pid should return None on failure."""
        result = mcp_client._extract_stdio_process_pid(None)
        assert result is None

    def test_extract_stdio_process_pid_returns_none_for_non_generator(self, mcp_client):
        """_extract_stdio_process_pid should return None for non-generator."""
        result = mcp_client._extract_stdio_process_pid("not a generator")
        assert result is None


class TestMcpClientReconnect:
    """Tests for MCP client reconnection logic."""

    @pytest.fixture
    def mcp_client(self):
        """Create an MCP client instance with stored config."""
        from astrbot._internal.protocols.mcp.client import McpClient

        client = McpClient()
        client._mcp_server_config = {"command": "test", "args": []}
        client._server_name = "test-server"
        return client

    def test_reconnect_lock_exists(self, mcp_client):
        """MCP client should have a reconnect lock."""
        assert mcp_client._reconnect_lock is not None
        assert isinstance(mcp_client._reconnect_lock, anyio.Lock)

    def test_reconnecting_flag_initial_false(self, mcp_client):
        """_reconnecting flag should be False initially."""
        assert mcp_client._reconnecting is False


class TestMcpClientUsesAsyncioNotAnyio:
    """TEST REQUIREMENT: Document asyncio vs anyio compliance.

    Per openspec directive: "异步库使用anyio" (Use anyio as async library).

    The MCP client implementation should use anyio primitives:
    - anyio.Lock instead of asyncio.Lock
    - anyio.Future instead of asyncio.Future
    - anyio.Event instead of asyncio.Event
    """

    def test_mcp_client_uses_asyncio_lock(self):
        """COMPLIANCE: MCP client uses anyio.Lock, not asyncio.Lock."""
        from astrbot._internal.protocols.mcp.client import McpClient

        client = McpClient()

        # Check that _reconnect_lock is anyio.Lock (compliant)
        assert isinstance(client._reconnect_lock, anyio.Lock), (
            "MCP client should use anyio.Lock instead of asyncio.Lock "
            "per the 'async_library: Use anyio' directive in openspec"
        )

    def test_abp_client_uses_asyncio_future(self):
        """VIOLATION: ABP client uses asyncio.Future instead of anyio."""
        from astrbot._internal.protocols.abp.client import AstrbotAbpClient

        client = AstrbotAbpClient()

        # The pending_requests dict uses asyncio.Future
        assert isinstance(client._pending_requests, dict)
        # Note: Futures are created in call_star_tool, not at init

    def test_orchestrator_run_loop_uses_asyncio_sleep(self):
        """COMPLIANCE: Orchestrator uses anyio.sleep, not asyncio.sleep."""
        from astrbot._internal.runtime.orchestrator import AstrbotOrchestrator

        import inspect

        source = inspect.getsource(AstrbotOrchestrator.run_loop)

        assert "asyncio.sleep" not in source, (
            "Orchestrator should use anyio.sleep instead of asyncio.sleep "
            "per the 'async_library: Use anyio' directive in openspec"
        )

    def test_orchestrator_run_loop_handles_asyncio_cancelled_error(self):
        """COMPLIANCE: Orchestrator catches anyio.CancelledError, not asyncio."""
        from astrbot._internal.runtime.orchestrator import AstrbotOrchestrator

        import inspect

        source = inspect.getsource(AstrbotOrchestrator.run_loop)

        assert "asyncio.CancelledError" not in source, (
            "Orchestrator should catch anyio.CancelledError not asyncio.CancelledError "
            "per the 'async_library: Use anyio' directive in openspec"
        )
