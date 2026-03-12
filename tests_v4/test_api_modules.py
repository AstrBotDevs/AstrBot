"""
Tests for API module exports and re-exports.
"""

from __future__ import annotations


class TestApiStarModule:
    """Tests for api/star module exports."""

    def test_star_module_exports_context(self):
        """api.star should export Context."""
        from astrbot_sdk.api.star import Context

        assert Context is not None

    def test_star_context_is_legacy_context(self):
        """api.star.Context should be LegacyContext."""
        from astrbot_sdk._legacy_api import LegacyContext
        from astrbot_sdk.api.star import Context

        assert Context is LegacyContext

    def test_star_module_exports_metadata(self):
        """api.star should export StarMetadata."""
        from astrbot_sdk.api.star import StarMetadata

        metadata = StarMetadata(name="demo", version="1.0.0")
        assert metadata.name == "demo"
        assert metadata.version == "1.0.0"


class TestApiComponentsModule:
    """Tests for api/components module exports."""

    def test_components_module_exports_command_component(self):
        """api.components should export CommandComponent."""
        from astrbot_sdk.api.components import CommandComponent

        assert CommandComponent is not None

    def test_command_component_is_from_legacy_api(self):
        """api.components.CommandComponent should be from _legacy_api."""
        from astrbot_sdk._legacy_api import CommandComponent as LegacyCommandComponent
        from astrbot_sdk.api.components import CommandComponent

        assert CommandComponent is LegacyCommandComponent


class TestApiEventModule:
    """Tests for api/event module exports."""

    def test_event_module_exports(self):
        """api.event should export expected names."""
        from astrbot_sdk.api.event import ADMIN, AstrMessageEvent, filter

        assert ADMIN == "admin"
        assert filter is not None
        assert AstrMessageEvent is not None

    def test_astr_message_event_is_message_event_subclass(self):
        """AstrMessageEvent should be a MessageEvent-compatible subclass."""
        from astrbot_sdk.api.event import AstrMessageEvent
        from astrbot_sdk.events import MessageEvent

        assert issubclass(AstrMessageEvent, MessageEvent)

    def test_all_exports(self):
        """api.event should export all expected names."""
        from astrbot_sdk.api.event import __all__

        assert "ADMIN" in __all__
        assert "AstrMessageEvent" in __all__
        assert "filter" in __all__

    def test_event_module_exports_legacy_types(self):
        """api.event should expose common legacy helper types."""
        from astrbot_sdk.api.event import (
            MessageEventResult,
            MessageSession,
            MessageType,
        )

        assert MessageEventResult is not None
        assert MessageSession is not None
        assert MessageType is not None


class TestApiModule:
    """Tests for top-level api module."""

    def test_api_module_exists(self):
        """api module should be importable."""
        import astrbot_sdk.api

        assert astrbot_sdk.api is not None

    def test_api_subpackages_exist(self):
        """New compat subpackages should be importable."""
        from astrbot_sdk.api import basic, message, platform, provider

        assert basic is not None
        assert message is not None
        assert platform is not None
        assert provider is not None
