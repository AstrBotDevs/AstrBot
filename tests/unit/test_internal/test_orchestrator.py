"""
Tests for AstrbotOrchestrator - core runtime lifecycle manager.

These tests verify:
1. Orchestrator initializes all protocol clients
2. Lifecycle states (INIT -> RUNNING -> SHUTDOWN)
3. Star registration/unregistration
4. Shutdown sequence
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAstrbotOrchestrator:
    """Test suite for AstrbotOrchestrator."""

    @pytest.fixture
    def orchestrator(self):
        """Create an orchestrator instance."""
        from astrbot._internal.runtime.orchestrator import AstrbotOrchestrator

        return AstrbotOrchestrator()

    @pytest.fixture
    def mock_star(self):
        """Create a mock star."""
        star = MagicMock()
        star.call_tool = AsyncMock(return_value={"result": "success"})
        return star

    def test_init_creates_all_protocol_clients(self, orchestrator):
        """Orchestrator should create LSP, MCP, ACP, ABP clients on init."""
        assert hasattr(orchestrator, "lsp")
        assert hasattr(orchestrator, "mcp")
        assert hasattr(orchestrator, "acp")
        assert hasattr(orchestrator, "abp")

    def test_init_running_false(self, orchestrator):
        """_running should be False on initialization."""
        assert orchestrator._running is False

    def test_running_property(self, orchestrator):
        """running property should return _running state."""
        assert orchestrator.running is False
        orchestrator._running = True
        assert orchestrator.running is True

    @pytest.mark.asyncio
    async def test_start_sets_running_true(self, orchestrator):
        """start() should set _running to True and connect all clients."""
        with patch.object(orchestrator.lsp, "connect", new_callable=AsyncMock) as mock_lsp, \
             patch.object(orchestrator.mcp, "connect", new_callable=AsyncMock) as mock_mcp, \
             patch.object(orchestrator.acp, "connect", new_callable=AsyncMock) as mock_acp, \
             patch.object(orchestrator.abp, "connect", new_callable=AsyncMock) as mock_abp:

            await orchestrator.start()

            assert orchestrator._running is True
            mock_lsp.assert_called_once()
            mock_mcp.assert_called_once()
            mock_acp.assert_called_once()
            mock_abp.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_star(self, orchestrator, mock_star):
        """register_star should add star to registry and ABP client."""
        await orchestrator.register_star("test-star", mock_star)

        assert "test-star" in orchestrator._stars
        assert orchestrator._stars["test-star"] is mock_star
        assert "test-star" in orchestrator.abp._stars

    @pytest.mark.asyncio
    async def test_unregister_star(self, orchestrator, mock_star):
        """unregister_star should remove star from registry and ABP client."""
        await orchestrator.register_star("test-star", mock_star)
        await orchestrator.unregister_star("test-star")

        assert "test-star" not in orchestrator._stars
        assert "test-star" not in orchestrator.abp._stars

    @pytest.mark.asyncio
    async def test_get_star(self, orchestrator, mock_star):
        """get_star should return registered star."""
        await orchestrator.register_star("test-star", mock_star)

        result = await orchestrator.get_star("test-star")
        assert result is mock_star

    @pytest.mark.asyncio
    async def test_get_star_not_found(self, orchestrator):
        """get_star should return None for non-existent star."""
        result = await orchestrator.get_star("non-existent")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_stars(self, orchestrator, mock_star):
        """list_stars should return list of registered star names."""
        await orchestrator.register_star("star-1", mock_star)
        await orchestrator.register_star("star-2", mock_star)

        result = await orchestrator.list_stars()
        # RuntimeStatusStar is auto-registered, so check membership instead of exact match
        assert "star-1" in result
        assert "star-2" in result

    @pytest.mark.asyncio
    async def test_shutdown_sequence(self, orchestrator):
        """shutdown() should call shutdown on all protocol clients."""
        with patch.object(orchestrator.lsp, "shutdown", new_callable=AsyncMock) as mock_lsp, \
             patch.object(orchestrator.mcp, "cleanup", new_callable=AsyncMock) as mock_mcp, \
             patch.object(orchestrator.acp, "shutdown", new_callable=AsyncMock) as mock_acp, \
             patch.object(orchestrator.abp, "shutdown", new_callable=AsyncMock) as mock_abp:

            orchestrator._running = True
            await orchestrator.shutdown()

            mock_lsp.assert_called_once()
            mock_mcp.assert_called_once()
            mock_acp.assert_called_once()
            mock_abp.assert_called_once()
            assert orchestrator._running is False

    @pytest.mark.asyncio
    async def test_run_loop_starts_and_stops(self, orchestrator):
        """run_loop should set _running True and exit on CancelledError."""
        async def stop_loop_soon():
            await asyncio.sleep(0.1)
            orchestrator._running = False

        asyncio.create_task(stop_loop_soon())

        await orchestrator.run_loop()

        # Should have run loop that exits cleanly
        assert True  # If we get here without exception, test passes

    @pytest.mark.asyncio
    async def test_run_loop_uses_asyncio_sleep(self, orchestrator):
        """TEST REQUIREMENT: run_loop currently uses asyncio.sleep, not anyio.

        This is a VIOLATION of the openspec directive which states:
        "异步库使用anyio" (Use anyio as the async library).

        The implementation should use anyio.sleep or anyio.Event.wait()
        instead of asyncio.sleep in the run_loop.
        """
        import ast
        import inspect

        source = inspect.getsource(orchestrator.run_loop)

        # Check that asyncio.sleep is NOT used (COMPLIANCE)
        uses_asyncio_sleep = "asyncio.sleep" in source

        # This assertion documents compliance
        assert not uses_asyncio_sleep, (
            "run_loop should use anyio.sleep instead of asyncio.sleep "
            "per the 'async_library: Use anyio' directive in openspec"
        )


class TestOrchestratorIntegration:
    """Integration tests for orchestrator with mock protocol clients."""

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_mocks(self):
        """Test complete lifecycle: init -> start -> run_loop -> shutdown."""
        from astrbot._internal.runtime.orchestrator import AstrbotOrchestrator

        orchestrator = AstrbotOrchestrator()

        # Mock all protocol client operations
        for client_name in ["lsp", "mcp", "acp", "abp"]:
            client = getattr(orchestrator, client_name)
            if hasattr(client, "connect"):
                client.connect = AsyncMock()
            if hasattr(client, "shutdown"):
                client.shutdown = AsyncMock()
            if hasattr(client, "cleanup"):
                client.cleanup = AsyncMock()

        # Start
        await orchestrator.start()
        assert orchestrator.running is True

        # Register a star
        mock_star = MagicMock()
        mock_star.call_tool = AsyncMock(return_value="ok")
        await orchestrator.register_star("test-star", mock_star)

        # Verify star is registered
        assert await orchestrator.get_star("test-star") is mock_star

        # Stop run_loop after a brief moment
        async def stop_after_delay():
            await asyncio.sleep(0.1)
            orchestrator._running = False

        asyncio.create_task(stop_after_delay())

        # Run loop
        await orchestrator.run_loop()

        # Shutdown
        await orchestrator.shutdown()
        assert orchestrator.running is False
