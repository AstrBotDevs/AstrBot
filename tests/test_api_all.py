"""Comprehensive tests for API modules."""

import pytest


class TestApiAll:
    """Tests for API re-exports."""

    @pytest.mark.parametrize(
        "symbol_name",
        [
            "AstrBotConfig",
            "html_renderer",
            "llm_tool",
            "MessageEventResult",
            "MessageChain",
            "CommandResult",
            "EventResultType",
            "AstrMessageEvent",
            "Platform",
            "AstrBotMessage",
            "MessageMember",
            "MessageType",
            "PlatformMetadata",
            "command",
            "command_group",
            "event_message_type",
            "regex",
            "platform_adapter_type",
            "EventMessageTypeFilter",
            "EventMessageType",
            "PlatformAdapterTypeFilter",
            "PlatformAdapterType",
            "Provider",
            "ProviderMetaData",
            "Personality",
            "Context",
            "Star",
        ],
    )
    def test_api_all_imports(self, symbol_name: str) -> None:
        """Verify every public symbol covered by the API import smoke tests."""
        from importlib import import_module

        assert getattr(import_module("astrbot.api.all"), symbol_name) is not None


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

        assert hasattr(event_filter, "__all__")


class TestApiUtil:
    """Tests for API util module."""

    def test_api_util_exists(self):
        """Test API util module exists."""
        from astrbot.api import util

        assert hasattr(util, "__all__")
