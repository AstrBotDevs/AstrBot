"""Tests for the warning emitted when a configured provider is substituted."""

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
    provider.terminate = AsyncMock()
    return provider


def _openai_config(provider_id: str) -> dict:
    """Chat completion provider config that loads without network access.

    Args:
        provider_id: Provider ID to register.

    Returns:
        A configuration accepted by ``ProviderManager.load_provider``.
    """
    return {
        "id": provider_id,
        "type": "openai_chat_completion",
        "provider_type": "chat_completion",
        "api_base": "https://example.invalid/v1",
        "key": ["sk-not-a-real-key"],
        "model": "test-model",
        "enable": True,
    }


def _chat_conf(provider_id: str) -> dict:
    """Chat provider selection, as the current configuration schema stores it.

    A local agent runner keeps the selected chat provider under
    ``agent_runner.config.model.provider_id``; any other runner type has no
    configured chat provider at all.

    Args:
        provider_id: The configured chat provider ID ("" when unset).

    Returns:
        A configuration mapping accepted by ``ProviderManager``.
    """
    return {
        "agent_runner": {
            "runner_type": "local",
            "config": {"model": {"provider_id": provider_id}},
        }
    }


def _build_manager(conf: dict) -> ProviderManager:
    """Build a manager through the real constructor.

    The fallback warning bookkeeping is initialised in ``ProviderManager.__init__``,
    so a manager assembled field by field would hide a missing initialisation.

    Args:
        conf: Configuration keys layered over an otherwise empty configuration.

    Returns:
        A manager that resolves providers from ``conf``.
    """
    config = {
        "provider": [],
        "provider_sources": [],
        "provider_settings": {},
    }
    config.update(conf)
    acm = MagicMock()
    acm.confs = {"default": config}
    acm.get_conf.return_value = config
    persona_mgr = MagicMock()
    persona_mgr.default_persona = ""
    return ProviderManager(acm, MagicMock(), persona_mgr)


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


class TestChatProviderFallbackWarning:
    def test_warns_when_configured_provider_is_substituted(self, caplog):
        """A configured-but-missing provider must not be replaced silently."""
        fallback = _make_provider("vision-only-model")
        manager = _build_manager(_chat_conf("my-chat"))
        manager.provider_insts = [fallback]

        with caplog.at_level(logging.WARNING):
            provider = manager.get_using_provider(ProviderType.CHAT_COMPLETION)

        assert provider is fallback
        assert "my-chat" in caplog.text
        assert "vision-only-model" in caplog.text

    def test_warning_is_emitted_only_once(self, caplog):
        """Repeated lookups must not flood the log."""
        manager = _build_manager(_chat_conf("my-chat"))
        manager.provider_insts = [_make_provider("other")]

        with caplog.at_level(logging.WARNING):
            for _ in range(5):
                manager.get_using_provider(ProviderType.CHAT_COMPLETION)

        assert caplog.text.count(FALLBACK_MESSAGE) == 1

    def test_distinct_substitutions_are_warned_separately(self, caplog):
        """Deduplication is per substituted provider, not global."""
        conf = _chat_conf("my-chat")
        manager = _build_manager(conf)
        manager.provider_insts = [_make_provider("other")]

        with caplog.at_level(logging.WARNING):
            manager.get_using_provider(ProviderType.CHAT_COMPLETION)
            conf["agent_runner"]["config"]["model"]["provider_id"] = "second-chat"
            manager.get_using_provider(ProviderType.CHAT_COMPLETION)
            # A different fallback is a different situation as well.
            manager.provider_insts = [_make_provider("third")]
            manager.get_using_provider(ProviderType.CHAT_COMPLETION)

        assert caplog.text.count(FALLBACK_MESSAGE) == 3

    def test_no_warning_when_configured_provider_resolves(self, caplog):
        """The happy path must stay quiet."""
        configured = _make_provider("my-chat")
        manager = _build_manager(_chat_conf("my-chat"))
        manager.inst_map = {"my-chat": configured}
        manager.provider_insts = [configured]

        with caplog.at_level(logging.WARNING):
            provider = manager.get_using_provider(ProviderType.CHAT_COMPLETION)

        assert provider is configured
        assert caplog.text == ""

    def test_no_warning_when_no_default_is_configured(self, caplog):
        """An unset default already has a dedicated startup warning."""
        fallback = _make_provider("first-one")
        manager = _build_manager(_chat_conf(""))
        manager.provider_insts = [fallback]

        with caplog.at_level(logging.WARNING):
            provider = manager.get_using_provider(ProviderType.CHAT_COMPLETION)

        assert provider is fallback
        assert caplog.text == ""

    def test_existing_not_found_warning_still_fires(self, caplog):
        """With no provider at all, the original message is kept."""
        manager = _build_manager(_chat_conf("my-chat"))

        with caplog.at_level(logging.WARNING):
            provider = manager.get_using_provider(ProviderType.CHAT_COMPLETION)

        assert provider is None
        assert "was not found" in caplog.text


class TestSttTtsProviderFallbackWarning:
    def test_stt_substitution_warns(self, caplog):
        fallback = _make_provider("other-stt")
        manager = _build_manager(
            {"provider_stt_settings": {"enable": True, "provider_id": "my-stt"}}
        )
        manager.stt_provider_insts = [fallback]

        with caplog.at_level(logging.WARNING):
            provider = manager.get_using_provider(ProviderType.SPEECH_TO_TEXT)

        assert provider is fallback
        assert "my-stt" in caplog.text
        assert "other-stt" in caplog.text

    def test_tts_substitution_warns(self, caplog):
        fallback = _make_provider("other-tts")
        manager = _build_manager(
            {"provider_tts_settings": {"enable": True, "provider_id": "my-tts"}}
        )
        manager.tts_provider_insts = [fallback]

        with caplog.at_level(logging.WARNING):
            provider = manager.get_using_provider(ProviderType.TEXT_TO_SPEECH)

        assert provider is fallback
        assert "my-tts" in caplog.text
        assert "other-tts" in caplog.text

    def test_disabled_stt_returns_none_without_warning(self, caplog):
        manager = _build_manager(
            {"provider_stt_settings": {"enable": False, "provider_id": "my-stt"}}
        )
        manager.stt_provider_insts = [_make_provider("other-stt")]

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
    def test_reported_as_unknown(self, caplog, fallback):
        manager = _build_manager(_chat_conf("my-chat"))
        manager.provider_insts = [fallback]

        with caplog.at_level(logging.WARNING):
            provider = manager.get_using_provider(ProviderType.CHAT_COMPLETION)

        assert provider is fallback
        assert "my-chat" in caplog.text
        assert "`unknown`" in caplog.text

    def test_unknown_key_still_deduplicates(self, caplog):
        manager = _build_manager(_chat_conf("my-chat"))
        manager.provider_insts = [_BareProvider()]

        with caplog.at_level(logging.WARNING):
            for _ in range(3):
                manager.get_using_provider(ProviderType.CHAT_COMPLETION)

        assert caplog.text.count(FALLBACK_MESSAGE) == 1


class TestFallbackWarningLifecycle:
    """A substitution that comes back after a provider change is reported again."""

    @pytest.mark.asyncio
    async def test_reload_clears_the_dedup_record(self, caplog):
        """A reload that drops a provider must re-arm the warning."""
        fallback = _make_provider("other")
        manager = _build_manager(_chat_conf("my-chat"))
        manager.inst_map = {"other": fallback}
        manager.provider_insts = [fallback]

        with caplog.at_level(logging.WARNING):
            for _ in range(2):
                manager.get_using_provider(ProviderType.CHAT_COMPLETION)
        assert caplog.text.count(FALLBACK_MESSAGE) == 1

        # Drive the real reload() and its provider teardown, so a missing reset
        # in the removal path breaks this test.
        with patch.object(
            manager_module,
            "astrbot_config",
            {"provider": [], "provider_sources": []},
        ):
            await manager.reload({"id": "my-chat", "enable": False})

        assert "other" not in manager.inst_map

        caplog.clear()
        with caplog.at_level(logging.WARNING):
            manager.get_using_provider(ProviderType.CHAT_COMPLETION)
        assert caplog.text.count(FALLBACK_MESSAGE) == 1

    @pytest.mark.asyncio
    async def test_deleted_provider_substitution_is_reported_again(self, caplog):
        """Re-creating and deleting a provider must not silence the new fallback.

        Adding a provider from the dashboard loads it without reloading the whole
        provider set, and deleting it only terminates the instance, so the record
        has to be reset by the provider teardown itself.
        """
        manager = _build_manager(_chat_conf("my-chat"))
        await manager.load_provider(_openai_config("other"))

        with caplog.at_level(logging.WARNING):
            for _ in range(2):
                manager.get_using_provider(ProviderType.CHAT_COMPLETION)
        assert caplog.text.count(FALLBACK_MESSAGE) == 1

        # The configured provider is created, so the substitution ends ...
        await manager.load_provider(_openai_config("my-chat"))
        provider = manager.get_using_provider(ProviderType.CHAT_COMPLETION)
        assert provider.provider_config["id"] == "my-chat"

        # ... and later deleted again, which starts a fresh substitution.
        await manager.terminate_provider("my-chat")

        caplog.clear()
        with caplog.at_level(logging.WARNING):
            provider = manager.get_using_provider(ProviderType.CHAT_COMPLETION)
        assert provider.provider_config["id"] == "other"
        assert caplog.text.count(FALLBACK_MESSAGE) == 1

        await manager.terminate_provider("other")

    @pytest.mark.asyncio
    async def test_failed_lookup_does_not_reset_the_dedup_record(self, caplog):
        """A no-op teardown must not turn the warning back on."""
        manager = _build_manager(_chat_conf("my-chat"))
        manager.provider_insts = [_make_provider("other")]

        with caplog.at_level(logging.WARNING):
            manager.get_using_provider(ProviderType.CHAT_COMPLETION)

        await manager.terminate_provider("missing")

        caplog.clear()
        with caplog.at_level(logging.WARNING):
            manager.get_using_provider(ProviderType.CHAT_COMPLETION)
        assert caplog.text == ""
