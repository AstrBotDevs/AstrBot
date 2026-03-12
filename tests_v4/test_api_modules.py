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

    def test_astr_message_event_is_message_event(self):
        """AstrMessageEvent should be MessageEvent."""
        from astrbot_sdk.api.event import AstrMessageEvent
        from astrbot_sdk.events import MessageEvent

        assert AstrMessageEvent is MessageEvent

    def test_all_exports(self):
        """api.event should export all expected names."""
        from astrbot_sdk.api.event import __all__

        assert "ADMIN" in __all__
        assert "AstrMessageEvent" in __all__
        assert "filter" in __all__


class TestApiModule:
    """Tests for top-level api module."""

    def test_api_module_exists(self):
        """api module should be importable."""
        import astrbot_sdk.api

        assert astrbot_sdk.api is not None
