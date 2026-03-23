"""Comprehensive tests for API modules."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class TestApiAll:
    """Tests for API re-exports."""

    def test_api_all_imports(self):
        """Test that API module imports work."""
        from astrbot.api.all import AstrBotConfig
        from astrbot.api.all import html_renderer
        from astrbot.api.all import llm_tool

    def test_api_message_event_imports(self):
        """Test message event imports."""
        from astrbot.api.all import MessageEventResult
        from astrbot.api.all import MessageChain
        from astrbot.api.all import CommandResult
        from astrbot.api.all import EventResultType

    def test_api_platform_imports(self):
        """Test platform imports."""
        from astrbot.api.all import AstrMessageEvent
        from astrbot.api.all import Platform
        from astrbot.api.all import AstrBotMessage
        from astrbot.api.all import MessageMember
        from astrbot.api.all import MessageType
        from astrbot.api.all import PlatformMetadata

    def test_api_star_register_imports(self):
        """Test star register imports."""
        from astrbot.api.all import command
        from astrbot.api.all import command_group
        from astrbot.api.all import event_message_type
        from astrbot.api.all import regex
        from astrbot.api.all import platform_adapter_type

    def test_api_filter_imports(self):
        """Test filter imports."""
        from astrbot.api.all import EventMessageTypeFilter
        from astrbot.api.all import EventMessageType
        from astrbot.api.all import PlatformAdapterTypeFilter
        from astrbot.api.all import PlatformAdapterType

    def test_api_provider_imports(self):
        """Test provider imports."""
        from astrbot.api.all import Provider
        from astrbot.api.all import ProviderMetaData
        from astrbot.api.all import Personality

    def test_api_star_imports(self):
        """Test star imports."""
        from astrbot.api.all import Context
        from astrbot.api.all import Star


class TestApiMessageComponents:
    """Tests for API message components."""

    def test_message_components_imports(self):
        """Test that message components can be imported."""
        import astrbot.api.message_components as message_components
        # Module should be importable
        assert message_components is not None

    def test_message_component_types(self):
        """Test message component types exist."""
        # Just ensure imports work
        from astrbot.api import message_components
        assert message_components is not None


class TestApiEvent:
    """Tests for API event module."""

    def test_event_filter_imports(self):
        """Test event filter imports."""
        from astrbot.api.event import filter as event_filter
        assert hasattr(event_filter, '__all__')


class TestApiUtil:
    """Tests for API util module."""

    def test_api_util_exists(self):
        """Test API util module exists."""
        from astrbot.api import util
        assert hasattr(util, '__all__')
