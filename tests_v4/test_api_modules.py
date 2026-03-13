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
        from astrbot_sdk.api.star import Star, StarTools, register

        @register(name="demo", author="tester")
        class DemoStar(Star):
            pass

        assert Star is LegacyStar
        assert callable(StarTools.get_data_dir)
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
        from astrbot_sdk.api.event import ADMIN, AstrMessageEvent, MessageChain, filter

        assert ADMIN == "admin"
        assert filter is not None
        assert AstrMessageEvent is not None
        assert MessageChain is not None

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

    def test_astr_message_event_preserves_legacy_message_str_and_private_group_none(self):
        """AstrMessageEvent should expose message_str and return None for missing group."""
        from astrbot_sdk.api.event import AstrMessageEvent

        event = AstrMessageEvent(text="hello", user_id="user-1")

        assert event.message_str == "hello"
        assert event.get_group_id() is None

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
        from astrbot_sdk.protocol.descriptors import SessionRef

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
            SessionRef(conversation_id="session-1"),
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
        from loguru import logger

        from astrbot_sdk.api import (
            AstrBotConfig,
            basic,
            message,
            message_components,
            platform,
            provider,
        )

        assert AstrBotConfig is not None
        assert basic is not None
        assert logger is not None
        assert message is not None
        assert message_components is not None
        assert platform is not None
        assert provider is not None


class TestAstrbotImportAlias:
    """Tests for the legacy ``astrbot`` package-name alias."""

    def test_legacy_astrbot_api_exports(self):
        """astrbot.api should expose the old logger/config entrance."""
        from astrbot.api import AstrBotConfig, logger

        assert AstrBotConfig is not None
        assert logger is not None

    def test_legacy_astrbot_event_exports(self):
        """astrbot.api.event should expose MessageChain from the legacy location."""
        from astrbot.api.event import AstrMessageEvent, MessageChain, filter

        assert AstrMessageEvent is not None
        assert MessageChain is not None
        assert filter is not None

    def test_legacy_astrbot_star_exports(self):
        """astrbot.api.star should expose Context/Star/register/StarTools."""
        from astrbot.api.star import Context, Star, StarTools, register

        assert Context is not None
        assert Star is not None
        assert callable(StarTools.get_data_dir)
        assert callable(register)
