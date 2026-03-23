"""
Tests for ABP (AstrBot Protocol) client implementation.

ABP is the built-in plugin protocol for in-process star communication.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestAstrbotAbpClient:
    """Test suite for AstrbotAbpClient."""

    @pytest.fixture
    def abp_client(self):
        """Create an ABP client instance."""
        from astrbot._internal.protocols.abp.client import AstrbotAbpClient

        return AstrbotAbpClient()

    @pytest.fixture
    def mock_star(self):
        """Create a mock star with a call_tool method."""
        star = AsyncMock()
        star.call_tool = AsyncMock(return_value={"result": "success"})
        return star

    @pytest.mark.asyncio
    async def test_connected_property_false_initially(self, abp_client):
        """ABP client should not be connected on initialization."""
        assert abp_client.connected is False

    @pytest.mark.asyncio
    async def test_connect_sets_connected_true(self, abp_client):
        """Calling connect() should set connected to True."""
        await abp_client.connect()
        assert abp_client.connected is True

    @pytest.mark.asyncio
    async def test_register_star(self, abp_client, mock_star):
        """register_star should add star to internal registry."""
        abp_client.register_star("test-star", mock_star)
        assert "test-star" in abp_client._stars
        assert abp_client._stars["test-star"] is mock_star

    @pytest.mark.asyncio
    async def test_unregister_star(self, abp_client, mock_star):
        """unregister_star should remove star from registry."""
        abp_client.register_star("test-star", mock_star)
        abp_client.unregister_star("test-star")
        assert "test-star" not in abp_client._stars

    @pytest.mark.asyncio
    async def test_unregister_star_idempotent(self, abp_client):
        """unregister_star should not raise if star doesn't exist."""
        abp_client.unregister_star("non-existent-star")  # Should not raise
        assert True

    @pytest.mark.asyncio
    async def test_call_star_tool_success(self, abp_client, mock_star):
        """call_star_tool should delegate to star.call_tool."""
        await abp_client.connect()
        abp_client.register_star("test-star", mock_star)

        result = await abp_client.call_star_tool(
            "test-star", "test-tool", {"arg": "value"}
        )

        mock_star.call_tool.assert_called_once_with("test-tool", {"arg": "value"})
        assert result == {"result": "success"}

    @pytest.mark.asyncio
    async def test_call_star_tool_not_connected(self, abp_client, mock_star):
        """call_star_tool should raise if not connected."""
        abp_client.register_star("test-star", mock_star)

        with pytest.raises(RuntimeError, match="not connected"):
            await abp_client.call_star_tool("test-star", "test-tool", {})

    @pytest.mark.asyncio
    async def test_call_star_tool_star_not_found(self, abp_client):
        """call_star_tool should raise if star not found."""
        await abp_client.connect()

        with pytest.raises(ValueError, match="Star 'non-existent' not found"):
            await abp_client.call_star_tool("non-existent", "test-tool", {})

    @pytest.mark.asyncio
    async def test_shutdown_sets_connected_false(self, abp_client):
        """shutdown should set connected to False."""
        await abp_client.connect()
        await abp_client.shutdown()
        assert abp_client.connected is False

    @pytest.mark.asyncio
    async def test_shutdown_cancels_pending_requests(self, abp_client):
        """shutdown should cancel any pending requests."""
        await abp_client.connect()

        # Create a pending future
        future = MagicMock(done=MagicMock(return_value=False))
        future.cancel = MagicMock()
        abp_client._pending_requests["req-1"] = future

        await abp_client.shutdown()

        future.cancel.assert_called_once()
        assert len(abp_client._pending_requests) == 0
