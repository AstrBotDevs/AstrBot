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

    def test_astr_message_event_preserves_legacy_message_str_and_private_group_none(
        self,
    ):
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

    def test_legacy_astrbot_root_exports_logger(self):
        """astrbot root package should expose logger like the old package did."""
        from astrbot import logger

        assert logger is not None

    def test_legacy_astrbot_api_exports(self):
        """astrbot.api should expose the old logger/config entrance."""
        from astrbot.api import AstrBotConfig, llm_tool, logger, sp

        assert AstrBotConfig is not None
        assert logger is not None
        assert sp is not None
        assert callable(llm_tool)

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

    def test_legacy_astrbot_core_session_waiter_exports(self):
        """astrbot.core.utils.session_waiter should expose the compat waiter helpers."""
        from astrbot.core.utils.session_waiter import (
            SessionController,
            SessionWaiter,
            session_waiter,
        )

        assert SessionController is not None
        assert callable(SessionWaiter.trigger)
        assert callable(session_waiter)

    def test_legacy_astrbot_event_filter_module_exports(self):
        """astrbot.api.event.filter should be importable from the old module path."""
        from astrbot.api.event.filter import EventMessageType, command, llm_tool

        assert EventMessageType is not None
        assert callable(command)
        assert callable(llm_tool)

    def test_legacy_astrbot_platform_exports(self):
        """astrbot.api.platform should expose the common legacy platform types."""
        from astrbot.api.platform import (
            AstrBotMessage,
            AstrMessageEvent,
            MessageType,
            Platform,
            PlatformMetadata,
            register_platform_adapter,
        )

        assert AstrBotMessage is not None
        assert AstrMessageEvent is not None
        assert MessageType is not None
        assert Platform is not None
        assert PlatformMetadata is not None
        with pytest.raises(NotImplementedError, match="register_platform_adapter"):
            register_platform_adapter()

    def test_legacy_astrbot_provider_exports(self):
        """astrbot.api.provider should expose the common legacy provider types."""
        from astrbot.api.provider import (
            LLMResponse,
            Provider,
            ProviderMetaData,
            ProviderRequest,
            ProviderType,
            STTProvider,
        )

        meta = ProviderMetaData(id="demo")
        req = ProviderRequest(prompt="hello")

        assert LLMResponse is not None
        assert Provider is not None
        assert STTProvider is not None
        assert meta.id == "demo"
        assert req.prompt == "hello"
        assert ProviderType.CHAT_COMPLETION.value == "chat_completion"

    def test_legacy_astrbot_api_all_exports(self):
        """astrbot.api.all should remain importable from the old umbrella module."""
        from astrbot.api.all import (
            AstrMessageEvent,
            Context,
            LLMResponse,
            MessageChain,
            command,
            llm_tool,
            register,
            sp,
        )

        assert AstrMessageEvent is not None
        assert Context is not None
        assert LLMResponse is not None
        assert MessageChain is not None
        assert callable(command)
        assert callable(llm_tool)
        assert callable(register)
        assert sp is not None

    def test_legacy_astrbot_util_exports(self):
        """astrbot.api.util should expose the waiter helpers from the old path."""
        from astrbot.api.util import SessionController, SessionWaiter, session_waiter

        assert SessionController is not None
        assert callable(SessionWaiter.trigger)
        assert callable(session_waiter)

    @pytest.mark.asyncio
    async def test_legacy_astrbot_sp_roundtrip(self):
        """astrbot.api.sp should provide a usable in-memory compat store."""
        from astrbot.api import sp

        await sp.global_put("feature_flag", True)
        assert await sp.global_get("feature_flag", False) is True

        await sp.session_put("umo:test", "counter", 3)
        assert await sp.session_get("umo:test", "counter", 0) == 3

        await sp.session_remove("umo:test", "counter")
        assert await sp.session_get("umo:test", "counter", 0) == 0
