"""Tests for the warning emitted when a configured provider is substituted."""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# astrbot.core.provider.manager and astrbot.core.star.context import each other,
# so the package entry point has to be imported first.
import astrbot.api  # noqa: F401
from astrbot.core.provider import manager as manager_module
from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.manager import ProviderManager

FALLBACK_MESSAGE = "is not available; falling back to"


def _make_provider(provider_id: str) -> MagicMock:
    provider = MagicMock()
    provider.provider_config = {"id": provider_id}
    return provider


class _BareProvider:
    """A provider stub without auto-created attributes.

    MagicMock would synthesise `provider_config` on access, which hides the
    branch that reports an unidentifiable fallback as `unknown`.
    """

    def __init__(self, provider_config=None):
        if provider_config is not None:
            self.provider_config = provider_config

    def meta(self):
        return MagicMock()


@pytest.fixture
def manager() -> ProviderManager:
    """Build a ProviderManager without running its heavy __init__."""
    mgr = ProviderManager.__new__(ProviderManager)
    mgr.inst_map = {}
    mgr.provider_insts = []
    mgr.stt_provider_insts = []
    mgr.tts_provider_insts = []
    mgr._fallback_warned = set()
    mgr.acm = MagicMock()
    return mgr


def _set_conf(manager: ProviderManager, conf: dict) -> None:
    manager.acm.get_conf = MagicMock(return_value=conf)


class TestChatProviderFallbackWarning:
    def test_warns_when_configured_provider_is_substituted(self, manager, caplog):
        """A configured-but-missing provider must not be replaced silently."""
        fallback = _make_provider("vision-only-model")
        manager.provider_insts = [fallback]
        _set_conf(manager, {"provider_settings": {"default_provider_id": "my-chat"}})

        with caplog.at_level(logging.WARNING):
            provider = manager.get_using_provider(ProviderType.CHAT_COMPLETION)

        assert provider is fallback
        assert "my-chat" in caplog.text
        assert "vision-only-model" in caplog.text

    def test_warning_is_emitted_only_once(self, manager, caplog):
        """Repeated lookups must not flood the log."""
        manager.provider_insts = [_make_provider("other")]
        _set_conf(manager, {"provider_settings": {"default_provider_id": "my-chat"}})

        with caplog.at_level(logging.WARNING):
            for _ in range(5):
                manager.get_using_provider(ProviderType.CHAT_COMPLETION)

        assert caplog.text.count("is not available; falling back to") == 1

    def test_no_warning_when_configured_provider_resolves(self, manager, caplog):
        """The happy path must stay quiet."""
        configured = _make_provider("my-chat")
        manager.inst_map = {"my-chat": configured}
        manager.provider_insts = [configured]
        _set_conf(manager, {"provider_settings": {"default_provider_id": "my-chat"}})

        with caplog.at_level(logging.WARNING):
            provider = manager.get_using_provider(ProviderType.CHAT_COMPLETION)

        assert provider is configured
        assert caplog.text == ""

    def test_no_warning_when_no_default_is_configured(self, manager, caplog):
        """An unset default already has a dedicated startup warning."""
        fallback = _make_provider("first-one")
        manager.provider_insts = [fallback]
        _set_conf(manager, {"provider_settings": {"default_provider_id": ""}})

        with caplog.at_level(logging.WARNING):
            provider = manager.get_using_provider(ProviderType.CHAT_COMPLETION)

        assert provider is fallback
        assert caplog.text == ""

    def test_existing_not_found_warning_still_fires(self, manager, caplog):
        """With no provider at all, the original message is kept."""
        _set_conf(manager, {"provider_settings": {"default_provider_id": "my-chat"}})

        with caplog.at_level(logging.WARNING):
            provider = manager.get_using_provider(ProviderType.CHAT_COMPLETION)

        assert provider is None
        assert "was not found" in caplog.text


class TestSttTtsProviderFallbackWarning:
    def test_stt_substitution_warns(self, manager, caplog):
        fallback = _make_provider("other-stt")
        manager.stt_provider_insts = [fallback]
        _set_conf(
            manager,
            {"provider_stt_settings": {"enable": True, "provider_id": "my-stt"}},
        )

        with caplog.at_level(logging.WARNING):
            provider = manager.get_using_provider(ProviderType.SPEECH_TO_TEXT)

        assert provider is fallback
        assert "my-stt" in caplog.text
        assert "other-stt" in caplog.text

    def test_tts_substitution_warns(self, manager, caplog):
        fallback = _make_provider("other-tts")
        manager.tts_provider_insts = [fallback]
        _set_conf(
            manager,
            {"provider_tts_settings": {"enable": True, "provider_id": "my-tts"}},
        )

        with caplog.at_level(logging.WARNING):
            provider = manager.get_using_provider(ProviderType.TEXT_TO_SPEECH)

        assert provider is fallback
        assert "my-tts" in caplog.text
        assert "other-tts" in caplog.text

    def test_disabled_stt_returns_none_without_warning(self, manager, caplog):
        manager.stt_provider_insts = [_make_provider("other-stt")]
        _set_conf(
            manager,
            {"provider_stt_settings": {"enable": False, "provider_id": "my-stt"}},
        )

        with caplog.at_level(logging.WARNING):
            provider = manager.get_using_provider(ProviderType.SPEECH_TO_TEXT)

        assert provider is None
        assert caplog.text == ""


class TestUnidentifiableFallback:
    """The fallback provider may not expose a usable ID."""

    @pytest.mark.parametrize(
        "fallback",
        [
            pytest.param(_BareProvider(), id="no-provider-config"),
            pytest.param(_BareProvider({}), id="empty-provider-config"),
        ],
    )
    def test_reported_as_unknown(self, manager, caplog, fallback):
        manager.provider_insts = [fallback]
        _set_conf(manager, {"provider_settings": {"default_provider_id": "my-chat"}})

        with caplog.at_level(logging.WARNING):
            provider = manager.get_using_provider(ProviderType.CHAT_COMPLETION)

        assert provider is fallback
        assert "my-chat" in caplog.text
        assert "`unknown`" in caplog.text

    def test_unknown_key_still_deduplicates(self, manager, caplog):
        manager.provider_insts = [_BareProvider()]
        _set_conf(manager, {"provider_settings": {"default_provider_id": "my-chat"}})

        with caplog.at_level(logging.WARNING):
            for _ in range(3):
                manager.get_using_provider(ProviderType.CHAT_COMPLETION)

        assert caplog.text.count(FALLBACK_MESSAGE) == 1


class TestFallbackWarningLifecycle:
    """A substitution that comes back after a reload must be reported again."""

    @pytest.mark.asyncio
    async def test_reload_clears_the_dedup_record(self, manager, caplog):
        manager.provider_insts = [_make_provider("other")]
        _set_conf(manager, {"provider_settings": {"default_provider_id": "my-chat"}})

        with caplog.at_level(logging.WARNING):
            for _ in range(2):
                manager.get_using_provider(ProviderType.CHAT_COMPLETION)
        assert caplog.text.count(FALLBACK_MESSAGE) == 1

        # Drive the real reload() so removing the clear() breaks this test.
        manager.reload_lock = asyncio.Lock()
        manager.terminate_provider = AsyncMock()
        manager.provider_sources_config = []
        manager.providers_config = []
        manager.curr_provider_inst = None
        manager.curr_stt_provider_inst = None
        manager.curr_tts_provider_inst = None
        with patch.object(
            manager_module,
            "astrbot_config",
            {"provider": [], "provider_sources": []},
        ):
            await manager.reload({"id": "my-chat", "enable": False})

        assert manager._fallback_warned == set()

        caplog.clear()
        with caplog.at_level(logging.WARNING):
            manager.get_using_provider(ProviderType.CHAT_COMPLETION)
        assert caplog.text.count(FALLBACK_MESSAGE) == 1
