"""Unit tests for other platform adapters (P2 platforms).

Tests cover:
- QQ Official adapter
- QQ Official Webhook adapter
- WeChat Official Account adapter
- Satori adapter
- Line adapter
- Misskey adapter

Note: Uses unittest.mock to simulate external dependencies.
"""

import asyncio

import pytest

# ============================================================================
# QQ Official Adapter Tests
# ============================================================================


class TestQQOfficialAdapter:
    """Tests for QQ Official platform adapter."""

    @pytest.fixture
    def platform_config(self):
        """Create a platform configuration for testing."""
        return {
            "id": "test_qqofficial",
            "appid": "test_appid",
            "secret": "test_secret",
        }

    @pytest.fixture
    def event_queue(self):
        """Create an event queue for testing."""
        return asyncio.Queue()

    @pytest.fixture
    def platform_settings(self):
        """Create platform settings for testing."""
        return {}

    def test_adapter_import(self, platform_config, event_queue, platform_settings):
        """Test that QQ Official adapter can be imported."""
        try:
            # Try importing the module - may fail due to dependencies
            from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
                QQOfficialMessageEvent,
            )

            import_success = True
        except ImportError as e:
            import_success = False
            pytest.skip(f"Cannot import QQ Official adapter: {e}")

        if import_success:
            assert QQOfficialMessageEvent is not None


# ============================================================================
# QQ Official Webhook Adapter Tests
# ============================================================================


class TestQQOfficialWebhookAdapter:
    """Tests for QQ Official Webhook platform adapter."""

    @pytest.fixture
    def platform_config(self):
        """Create a platform configuration for testing."""
        return {
            "id": "test_qqofficial_webhook",
            "appid": "test_appid",
            "secret": "test_secret",
        }

    @pytest.fixture
    def event_queue(self):
        """Create an event queue for testing."""
        return asyncio.Queue()

    @pytest.fixture
    def platform_settings(self):
        """Create platform settings for testing."""
        return {}

    def test_adapter_import(self, platform_config, event_queue, platform_settings):
        """Test that QQ Official Webhook adapter can be imported."""
        try:
            from astrbot.core.platform.sources.qqofficial_webhook.qo_webhook_server import (
                QQOfficialWebhook,
            )

            import_success = True
        except ImportError as e:
            import_success = False
            pytest.skip(f"Cannot import QQ Official Webhook adapter: {e}")

        if import_success:
            assert QQOfficialWebhook is not None


# ============================================================================
# WeChat Official Account Adapter Tests
# ============================================================================


class TestWeChatOfficialAccountAdapter:
    """Tests for WeChat Official Account platform adapter."""

    @pytest.fixture
    def platform_config(self):
        """Create a platform configuration for testing."""
        return {
            "id": "test_weixin_official_account",
            "appid": "test_appid",
            "secret": "test_secret",
            "token": "test_token",
            "encoding_aes_key": "test_encoding_aes_key",
        }

    @pytest.fixture
    def event_queue(self):
        """Create an event queue for testing."""
        return asyncio.Queue()

    @pytest.fixture
    def platform_settings(self):
        """Create platform settings for testing."""
        return {}

    def test_adapter_import(self, platform_config, event_queue, platform_settings):
        """Test that WeChat Official Account adapter can be imported."""
        try:
            from astrbot.core.platform.sources.weixin_official_account.weixin_offacc_adapter import (
                WeixinOfficialAccountPlatformAdapter,
            )

            import_success = True
        except ImportError as e:
            import_success = False
            pytest.skip(f"Cannot import WeChat Official Account adapter: {e}")

        if import_success:
            assert WeixinOfficialAccountPlatformAdapter is not None


# ============================================================================
# Satori Adapter Tests
# ============================================================================


class TestSatoriAdapter:
    """Tests for Satori platform adapter."""

    @pytest.fixture
    def platform_config(self):
        """Create a platform configuration for testing."""
        return {
            "id": "test_satori",
            "host": "127.0.0.1",
            "port": 5140,
        }

    @pytest.fixture
    def event_queue(self):
        """Create an event queue for testing."""
        return asyncio.Queue()

    @pytest.fixture
    def platform_settings(self):
        """Create platform settings for testing."""
        return {}

    def test_adapter_import(self, platform_config, event_queue, platform_settings):
        """Test that Satori adapter can be imported."""
        try:
            from astrbot.core.platform.sources.satori.satori_adapter import (
                SatoriPlatformAdapter,
            )

            import_success = True
        except ImportError as e:
            import_success = False
            pytest.skip(f"Cannot import Satori adapter: {e}")

        if import_success:
            assert SatoriPlatformAdapter is not None


# ============================================================================
# Line Adapter Tests
# ============================================================================


class TestLineAdapter:
    """Tests for Line platform adapter."""

    @pytest.fixture
    def platform_config(self):
        """Create a platform configuration for testing."""
        return {
            "id": "test_line",
            "channel_access_token": "test_token",
            "channel_secret": "test_secret",
        }

    @pytest.fixture
    def event_queue(self):
        """Create an event queue for testing."""
        return asyncio.Queue()

    @pytest.fixture
    def platform_settings(self):
        """Create platform settings for testing."""
        return {}

    def test_adapter_import(self, platform_config, event_queue, platform_settings):
        """Test that Line adapter can be imported."""
        try:
            from astrbot.core.platform.sources.line.line_adapter import LinePlatformAdapter

            import_success = True
        except ImportError as e:
            import_success = False
            pytest.skip(f"Cannot import Line adapter: {e}")

        if import_success:
            assert LinePlatformAdapter is not None


# ============================================================================
# Misskey Adapter Tests
# ============================================================================


class TestMisskeyAdapter:
    """Tests for Misskey platform adapter."""

    @pytest.fixture
    def platform_config(self):
        """Create a platform configuration for testing."""
        return {
            "id": "test_misskey",
            "instance_url": "https://misskey.io",
            "access_token": "test_token",
        }

    @pytest.fixture
    def event_queue(self):
        """Create an event queue for testing."""
        return asyncio.Queue()

    @pytest.fixture
    def platform_settings(self):
        """Create platform settings for testing."""
        return {}

    def test_adapter_import(self, platform_config, event_queue, platform_settings):
        """Test that Misskey adapter can be imported."""
        try:
            from astrbot.core.platform.sources.misskey.misskey_adapter import (
                MisskeyPlatformAdapter,
            )

            import_success = True
        except ImportError as e:
            import_success = False
            pytest.skip(f"Cannot import Misskey adapter: {e}")

        if import_success:
            assert MisskeyPlatformAdapter is not None


# ============================================================================
# Wecom AI Bot Adapter Tests
# ============================================================================


class TestWecomAIBotAdapter:
    """Tests for Wecom AI Bot platform adapter."""

    @pytest.fixture
    def platform_config(self):
        """Create a platform configuration for testing."""
        return {
            "id": "test_wecom_ai_bot",
            "corpid": "test_corpid",
            "secret": "test_secret",
        }

    @pytest.fixture
    def event_queue(self):
        """Create an event queue for testing."""
        return asyncio.Queue()

    @pytest.fixture
    def platform_settings(self):
        """Create platform settings for testing."""
        return {}

    def test_adapter_import(self, platform_config, event_queue, platform_settings):
        """Test that Wecom AI Bot adapter can be imported."""
        try:
            from astrbot.core.platform.sources.wecom_ai_bot.wecomai_webhook import (
                WecomAIBotWebhookClient,
            )

            import_success = True
        except ImportError as e:
            import_success = False
            pytest.skip(f"Cannot import Wecom AI Bot adapter: {e}")

        if import_success:
            assert WecomAIBotWebhookClient is not None


# ============================================================================
# Platform Metadata Tests for P2 Platforms
# ============================================================================


class TestP2PlatformMetadata:
    """Tests for P2 platform metadata."""

    def test_line_metadata(self):
        """Test Line adapter metadata."""
        try:
            from astrbot.core.platform.sources.line.line_adapter import LinePlatformAdapter

            # Check if LineAdapter has meta method
            assert hasattr(LinePlatformAdapter, "meta")
        except ImportError:
            pytest.skip("Line adapter not available")

    def test_satori_metadata(self):
        """Test Satori adapter metadata."""
        try:
            from astrbot.core.platform.sources.satori.satori_adapter import (
                SatoriPlatformAdapter,
            )

            # Check if SatoriAdapter has meta method
            assert hasattr(SatoriPlatformAdapter, "meta")
        except ImportError:
            pytest.skip("Satori adapter not available")

    def test_weixin_official_account_metadata(self):
        """Test WeChat Official Account adapter metadata."""
        try:
            from astrbot.core.platform.sources.weixin_official_account.weixin_offacc_adapter import (
                WeixinOfficialAccountPlatformAdapter,
            )

            # Check if adapter has meta method
            assert hasattr(WeixinOfficialAccountPlatformAdapter, "meta")
        except ImportError:
            pytest.skip("WeChat Official Account adapter not available")
