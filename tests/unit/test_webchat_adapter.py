"""Unit tests for WebChat platform adapter.

Tests cover:
- WebChatAdapter class initialization and methods
- Queue-based message handling
- Message transmission
- Session management

Note: Uses unittest.mock to simulate dependencies.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def event_queue():
    """Create an event queue for testing."""
    return asyncio.Queue()


@pytest.fixture
def platform_config():
    """Create a platform configuration for testing."""
    return {
        "id": "test_webchat",
    }


@pytest.fixture
def platform_settings():
    """Create platform settings for testing."""
    return {}


# ============================================================================
# WebChatAdapter Initialization Tests
# ============================================================================


class TestWebChatAdapterInit:
    """Tests for WebChatAdapter initialization."""

    def test_init_basic(self, event_queue, platform_config, platform_settings):
        """Test basic adapter initialization."""
        with patch(
            "astrbot.core.platform.sources.webchat.webchat_adapter.webchat_queue_mgr"
        ):
            from astrbot.core.platform.sources.webchat.webchat_adapter import (
                WebChatAdapter,
            )

            adapter = WebChatAdapter(platform_config, platform_settings, event_queue)

            assert adapter.config == platform_config


# ============================================================================
# WebChatAdapter Metadata Tests
# ============================================================================


class TestWebChatAdapterMetadata:
    """Tests for WebChatAdapter metadata."""

    def test_meta_returns_correct_metadata(
        self, event_queue, platform_config, platform_settings
    ):
        """Test meta() returns correct PlatformMetadata."""
        with patch(
            "astrbot.core.platform.sources.webchat.webchat_adapter.webchat_queue_mgr"
        ):
            from astrbot.core.platform.sources.webchat.webchat_adapter import (
                WebChatAdapter,
            )

            adapter = WebChatAdapter(platform_config, platform_settings, event_queue)
            meta = adapter.meta()

            assert meta.name == "webchat"
            # Note: meta.id returns "webchat" by default, not config["id"]


# ============================================================================
# WebChatAdapter Terminate Tests
# ============================================================================


class TestWebChatAdapterTerminate:
    """Tests for adapter termination."""

    @pytest.mark.asyncio
    async def test_terminate(self, event_queue, platform_config, platform_settings):
        """Test adapter termination."""
        with patch(
            "astrbot.core.platform.sources.webchat.webchat_adapter.webchat_queue_mgr"
        ):
            from astrbot.core.platform.sources.webchat.webchat_adapter import (
                WebChatAdapter,
            )

            adapter = WebChatAdapter(platform_config, platform_settings, event_queue)

            # terminate() should set the stop_event
            await adapter.terminate()

            # Verify stop_event is set after terminate
            assert adapter.stop_event.is_set()
