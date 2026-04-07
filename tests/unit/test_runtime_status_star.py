"""
Tests for RuntimeStatusStar ABP plugin.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot._internal.stars.runtime_status_star import RuntimeStatusStar


class TestRuntimeStatusStar:
    """Test suite for RuntimeStatusStar."""

    @pytest.fixture
    def mock_orchestrator(self) -> MagicMock:
        """Create a mock orchestrator."""
        orchestrator = MagicMock()
        orchestrator.running = True
        orchestrator.lsp.connected = True
        orchestrator.mcp.connected = True
        orchestrator.acp.connected = False
        orchestrator.abp.connected = True
        orchestrator.list_stars = AsyncMock(return_value=["star-a", "star-b"])
        orchestrator._message_count = 42
        orchestrator._last_activity_timestamp = 1710000000.0
        return orchestrator

    @pytest.fixture
    def star(self, mock_orchestrator: MagicMock) -> RuntimeStatusStar:
        """Create a RuntimeStatusStar with mock orchestrator."""
        star = RuntimeStatusStar()
        star.set_orchestrator(mock_orchestrator)
        return star

    @pytest.mark.anyio
    async def test_get_runtime_status(self, star: RuntimeStatusStar) -> None:
        """Test get_runtime_status tool returns running state and uptime."""
        result = await star.call_tool("get_runtime_status", {})

        assert isinstance(result, dict)
        assert "running" in result
        assert "uptime_seconds" in result
        assert result["running"] is True
        assert result["uptime_seconds"] >= 0

    @pytest.mark.anyio
    async def test_get_runtime_status_not_running(
        self, mock_orchestrator: MagicMock
    ) -> None:
        """Test get_runtime_status when orchestrator is not running."""
        mock_orchestrator.running = False
        star = RuntimeStatusStar()
        star.set_orchestrator(mock_orchestrator)

        result = await star.call_tool("get_runtime_status", {})

        assert result["running"] is False

    @pytest.mark.anyio
    async def test_get_protocol_status(self, star: RuntimeStatusStar) -> None:
        """Test get_protocol_status tool returns protocol client states."""
        result = await star.call_tool("get_protocol_status", {})

        assert isinstance(result, dict)
        assert "lsp" in result
        assert "mcp" in result
        assert "acp" in result
        assert "abp" in result

        assert result["lsp"]["connected"] is True
        assert result["mcp"]["connected"] is True
        assert result["acp"]["connected"] is False
        assert result["abp"]["connected"] is True

        # Verify name field
        assert result["lsp"]["name"] == "lsp-client"
        assert result["mcp"]["name"] == "mcp-client"
        assert result["acp"]["name"] == "acp-client"
        assert result["abp"]["name"] == "abp-client"

    @pytest.mark.anyio
    async def test_get_protocol_status_no_orchestrator(self) -> None:
        """Test get_protocol_status when no orchestrator is set."""
        star = RuntimeStatusStar()

        result = await star.call_tool("get_protocol_status", {})

        assert result["lsp"]["connected"] is False
        assert result["mcp"]["connected"] is False
        assert result["acp"]["connected"] is False
        assert result["abp"]["connected"] is False

    @pytest.mark.anyio
    async def test_get_star_registry(self, star: RuntimeStatusStar) -> None:
        """Test get_star_registry tool returns registered star names."""
        result = await star.call_tool("get_star_registry", {})

        assert isinstance(result, dict)
        assert "stars" in result
        assert result["stars"] == ["star-a", "star-b"]

    @pytest.mark.anyio
    async def test_get_star_registry_no_orchestrator(self) -> None:
        """Test get_star_registry when no orchestrator is set."""
        star = RuntimeStatusStar()

        result = await star.call_tool("get_star_registry", {})

        assert result["stars"] == []

    @pytest.mark.anyio
    async def test_get_stats(self, star: RuntimeStatusStar) -> None:
        """Test get_stats tool returns message counts and metrics."""
        result = await star.call_tool("get_stats", {})

        assert isinstance(result, dict)
        assert "uptime_seconds" in result
        assert result["uptime_seconds"] >= 0
        assert "total_messages" in result
        assert result["total_messages"] == 42
        assert "last_activity" in result
        assert result["last_activity"] is not None

    @pytest.mark.anyio
    async def test_unknown_tool(self, star: RuntimeStatusStar) -> None:
        """Test that unknown tool raises ValueError."""
        with pytest.raises(ValueError, match="Unknown tool"):
            await star.call_tool("unknown_tool", {})

    @pytest.mark.anyio
    async def test_record_activity(self) -> None:
        """Test orchestrator record_activity() increments message count."""
        from astrbot._internal.runtime.orchestrator import AstrbotOrchestrator

        orchestrator = AstrbotOrchestrator()
        assert orchestrator._message_count == 0

        orchestrator.record_activity()
        assert orchestrator._message_count == 1

        orchestrator.record_activity()
        orchestrator.record_activity()
        assert orchestrator._message_count == 3

        assert orchestrator._last_activity_timestamp is not None

        await orchestrator.shutdown()

    @pytest.mark.anyio
    async def test_star_name(self) -> None:
        """Test star has correct name and description."""
        star = RuntimeStatusStar()
        assert star.name == "runtime-status-star"
        assert "runtime" in star.description.lower()


class TestOrchestratorAutoRegistersRuntimeStatusStar:
    """Test that orchestrator auto-registers RuntimeStatusStar."""

    @pytest.mark.anyio
    async def test_orchestrator_registers_runtime_status_star(self) -> None:
        """Test orchestrator auto-registers the runtime-status-star."""
        from astrbot._internal.runtime.orchestrator import AstrbotOrchestrator

        orchestrator = AstrbotOrchestrator()

        # Check that runtime-status-star is in the registry
        assert "runtime-status-star" in orchestrator._stars

        # Check that the star is registered with ABP
        assert "runtime-status-star" in orchestrator.abp._stars

        # Check we can get the star
        star = await orchestrator.get_star("runtime-status-star")
        assert star is not None
        assert star.name == "runtime-status-star"

        await orchestrator.shutdown()

    @pytest.mark.anyio
    async def test_runtime_status_star_tools_via_abp(self) -> None:
        """Test calling RuntimeStatusStar tools via ABP client."""
        from astrbot._internal.runtime.orchestrator import AstrbotOrchestrator

        orchestrator = AstrbotOrchestrator()
        await orchestrator.start()

        # Call get_runtime_status via ABP
        result = await orchestrator.abp.call_star_tool(
            star_name="runtime-status-star",
            tool_name="get_runtime_status",
            arguments={},
        )

        assert isinstance(result, dict)
        assert "running" in result
        assert "uptime_seconds" in result

        await orchestrator.shutdown()

    @pytest.mark.anyio
    async def test_runtime_status_star_listed_in_stars(self) -> None:
        """Test runtime-status-star appears in list_stars()."""
        from astrbot._internal.runtime.orchestrator import AstrbotOrchestrator

        orchestrator = AstrbotOrchestrator()

        stars = await orchestrator.list_stars()
        assert "runtime-status-star" in stars

        await orchestrator.shutdown()
