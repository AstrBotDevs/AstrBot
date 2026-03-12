"""
Tests for clients/__init__.py - Module exports.
"""

from __future__ import annotations



class TestClientsModuleExports:
    """Tests for clients module exports."""

    def test_exports_db_client(self):
        """clients module should export DBClient."""
        from astrbot_sdk.clients import DBClient

        assert DBClient is not None

    def test_exports_llm_client(self):
        """clients module should export LLMClient."""
        from astrbot_sdk.clients import LLMClient

        assert LLMClient is not None

    def test_exports_llm_response(self):
        """clients module should export LLMResponse."""
        from astrbot_sdk.clients import LLMResponse

        assert LLMResponse is not None

    def test_exports_chat_message(self):
        """clients module should export ChatMessage."""
        from astrbot_sdk.clients import ChatMessage

        assert ChatMessage is not None

    def test_exports_memory_client(self):
        """clients module should export MemoryClient."""
        from astrbot_sdk.clients import MemoryClient

        assert MemoryClient is not None

    def test_exports_platform_client(self):
        """clients module should export PlatformClient."""
        from astrbot_sdk.clients import PlatformClient

        assert PlatformClient is not None

    def test_all_exports_defined(self):
        """__all__ should contain all expected exports."""
        from astrbot_sdk.clients import __all__

        assert "DBClient" in __all__
        assert "LLMClient" in __all__
        assert "LLMResponse" in __all__
        assert "ChatMessage" in __all__
        assert "MemoryClient" in __all__
        assert "PlatformClient" in __all__

    def test_does_not_export_capability_proxy(self):
        """CapabilityProxy should not be in public exports."""
        from astrbot_sdk.clients import __all__

        assert "CapabilityProxy" not in __all__

    def test_capability_proxy_importable_from_private(self):
        """CapabilityProxy should be importable from _proxy."""
        from astrbot_sdk.clients._proxy import CapabilityProxy

        assert CapabilityProxy is not None
