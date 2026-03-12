"""
Tests for API module exports and re-exports.
"""

from __future__ import annotations

import pytest


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

    def test_star_module_exports_legacy_star_and_register(self):
        """api.star should expose legacy Star/register imports."""
        from astrbot_sdk._legacy_api import LegacyStar
        from astrbot_sdk.api.star import Star, register

        @register(name="demo", author="tester")
        class DemoStar(Star):
            pass

        assert Star is LegacyStar
        assert callable(register)
        assert DemoStar.__astrbot_plugin_metadata__ == {
            "name": "demo",
            "author": "tester",
        }


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

    def test_message_chain_serializes_components(self):
        """MessageChain.to_payload() should preserve compat component fields."""
        from astrbot_sdk.api.message import Comp, MessageChain

        chain = MessageChain(
            [
                Comp.Plain(text="hello"),
                Comp.Image(file="https://example.com/image.png"),
            ]
        )

        assert chain.to_payload() == [
            {"type": "Plain", "text": "hello"},
            {"type": "Image", "file": "https://example.com/image.png"},
        ]

    @pytest.mark.asyncio
    async def test_astr_message_event_send_uses_send_chain_when_context_bound(self):
        """AstrMessageEvent.send() should use platform.send_chain for rich messages."""
        from unittest.mock import AsyncMock, MagicMock

        from astrbot_sdk.api.event import AstrMessageEvent
        from astrbot_sdk.api.message import Comp, MessageChain

        runtime_context = MagicMock()
        runtime_context.platform = AsyncMock()
        event = AstrMessageEvent(session_id="session-1", context=runtime_context)
        chain = MessageChain(
            [
                Comp.Plain(text="hello"),
                Comp.Image(file="https://example.com/image.png"),
            ]
        )

        await event.send(chain)

        runtime_context.platform.send_chain.assert_called_once_with(
            "session-1",
            [
                {"type": "Plain", "text": "hello"},
                {"type": "Image", "file": "https://example.com/image.png"},
            ],
        )


class TestApiModule:
    """Tests for top-level api module."""

    def test_api_module_exists(self):
        """api module should be importable."""
        import astrbot_sdk.api

        assert astrbot_sdk.api is not None

    def test_api_subpackages_exist(self):
        """New compat subpackages should be importable."""
        from astrbot_sdk.api import (
            basic,
            message,
            message_components,
            platform,
            provider,
        )

        assert basic is not None
        assert message is not None
        assert message_components is not None
        assert platform is not None
        assert provider is not None
