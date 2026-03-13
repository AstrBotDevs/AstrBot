"""Tests for LegacyContext metadata methods."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot_sdk._legacy_api import LegacyContext
from astrbot_sdk.context import Context as NewContext
from astrbot_sdk.clients.metadata import PluginMetadata


class TestLegacyContextMetadataMethods:
    """Tests for LegacyContext.get_registered_star and get_all_stars."""

    @pytest.fixture
    def legacy_context(self):
        """Create LegacyContext instance."""
        return LegacyContext("test_plugin")

    @pytest.fixture
    def mock_runtime_context(self):
        """Create mock runtime context with metadata client."""
        context = MagicMock(spec=NewContext)
        context.metadata = MagicMock()
        context.metadata.get_plugin = AsyncMock()
        context.metadata.list_plugins = AsyncMock()
        return context

    @pytest.mark.asyncio
    async def test_get_registered_star_returns_plugin_metadata(
        self, legacy_context, mock_runtime_context
    ):
        """get_registered_star should return plugin metadata."""
        expected = PluginMetadata(
            name="target_plugin",
            display_name="Target Plugin",
            description="Test",
            author="test",
            version="1.0.0",
        )
        mock_runtime_context.metadata.get_plugin.return_value = expected
        legacy_context.bind_runtime_context(mock_runtime_context)

        result = await legacy_context.get_registered_star("target_plugin")

        mock_runtime_context.metadata.get_plugin.assert_called_once_with(
            "target_plugin"
        )
        assert result == expected

    @pytest.mark.asyncio
    async def test_get_registered_star_returns_none_when_not_found(
        self, legacy_context, mock_runtime_context
    ):
        """get_registered_star should return None when plugin not found."""
        mock_runtime_context.metadata.get_plugin.return_value = None
        legacy_context.bind_runtime_context(mock_runtime_context)

        result = await legacy_context.get_registered_star("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_registered_star_raises_without_runtime_context(
        self, legacy_context
    ):
        """get_registered_star should raise when runtime context not bound."""
        with pytest.raises(RuntimeError, match="尚未绑定运行时 Context"):
            await legacy_context.get_registered_star("any_plugin")

    @pytest.mark.asyncio
    async def test_get_all_stars_returns_list(
        self, legacy_context, mock_runtime_context
    ):
        """get_all_stars should return list of plugin metadata."""
        expected = [
            PluginMetadata(
                name="plugin1",
                display_name="Plugin 1",
                description="Test",
                author="a1",
                version="1.0",
            ),
            PluginMetadata(
                name="plugin2",
                display_name="Plugin 2",
                description="Test",
                author="a2",
                version="2.0",
            ),
        ]
        mock_runtime_context.metadata.list_plugins.return_value = expected
        legacy_context.bind_runtime_context(mock_runtime_context)

        result = await legacy_context.get_all_stars()

        mock_runtime_context.metadata.list_plugins.assert_called_once()
        assert result == expected
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_all_stars_returns_empty_list(
        self, legacy_context, mock_runtime_context
    ):
        """get_all_stars should return empty list when no plugins."""
        mock_runtime_context.metadata.list_plugins.return_value = []
        legacy_context.bind_runtime_context(mock_runtime_context)

        result = await legacy_context.get_all_stars()

        assert result == []

    @pytest.mark.asyncio
    async def test_get_all_stars_raises_without_runtime_context(self, legacy_context):
        """get_all_stars should raise when runtime context not bound."""
        with pytest.raises(RuntimeError, match="尚未绑定运行时 Context"):
            await legacy_context.get_all_stars()
