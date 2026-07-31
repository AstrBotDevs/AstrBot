"""Tests for the warning emitted when a configured provider is substituted."""

import logging
from unittest.mock import MagicMock

import pytest

# astrbot.core.provider.manager and astrbot.core.star.context import each other,
# so the package entry point has to be imported first.
import astrbot.api  # noqa: F401
from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.manager import ProviderManager


def _make_provider(provider_id: str) -> MagicMock:
    provider = MagicMock()
    provider.provider_config = {"id": provider_id}
    return provider


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
