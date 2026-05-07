"""Tests for the provider-registry merge helper used by both
``GET /api/config/get`` and ``GET /api/config/provider/template``.
"""

from types import SimpleNamespace

import pytest

from astrbot.core.provider.entities import ProviderMetaData, ProviderType
from astrbot.core.provider.register import provider_registry
from astrbot.dashboard.routes.config import _merge_registered_providers_into


@pytest.fixture
def isolated_registry(monkeypatch):
    """Replace ``provider_registry`` with an empty list for each test."""
    fake: list = []
    monkeypatch.setattr(
        "astrbot.dashboard.routes.config.provider_registry",
        fake,
    )
    return fake


def _fake_pm(type_: str, default_config_tmpl) -> ProviderMetaData:
    return ProviderMetaData(
        id="default",
        model=None,
        type=type_,
        desc=type_,
        provider_type=ProviderType.TEXT_TO_SPEECH,
        cls_type=SimpleNamespace,
        default_config_tmpl=default_config_tmpl,
    )


def test_injects_plugin_provider(isolated_registry) -> None:
    isolated_registry.append(_fake_pm("plugin_tts", {"provider_type": "text_to_speech", "key": "v"}))
    tmpl: dict = {}
    _merge_registered_providers_into(tmpl)
    assert "plugin_tts" in tmpl
    assert tmpl["plugin_tts"]["provider_type"] == "text_to_speech"


def test_setdefault_protects_existing_entry(isolated_registry) -> None:
    """A plugin should not silently overwrite a core static template
    that happens to share the same key."""
    isolated_registry.append(_fake_pm("openai_compat", {"provider_type": "chat_completion", "src": "plugin"}))
    tmpl = {"openai_compat": {"provider_type": "chat_completion", "src": "core"}}
    _merge_registered_providers_into(tmpl)
    assert tmpl["openai_compat"]["src"] == "core"


def test_empty_dict_template_is_kept(isolated_registry) -> None:
    """``is not None`` check (rather than truthiness) — a plugin that
    registers with an intentionally empty default_config_tmpl should
    still surface in the picker."""
    isolated_registry.append(_fake_pm("blank_tts", {}))
    tmpl: dict = {}
    _merge_registered_providers_into(tmpl)
    assert "blank_tts" in tmpl
    assert tmpl["blank_tts"] == {}


def test_none_template_is_skipped(isolated_registry) -> None:
    """Providers that registered without supplying a default template
    should not appear in the picker."""
    isolated_registry.append(_fake_pm("no_tmpl", None))
    tmpl: dict = {}
    _merge_registered_providers_into(tmpl)
    assert tmpl == {}


def test_idempotent(isolated_registry) -> None:
    isolated_registry.append(_fake_pm("plugin_tts", {"x": 1}))
    tmpl: dict = {}
    _merge_registered_providers_into(tmpl)
    _merge_registered_providers_into(tmpl)
    assert list(tmpl.keys()) == ["plugin_tts"]


def test_real_registry_unaffected_by_helper_call(monkeypatch) -> None:
    """Smoke check that calling the helper against a real registry doesn't
    raise and yields a sensible dict."""
    tmpl: dict = {}
    _merge_registered_providers_into(tmpl)
    # Real registry may be empty in the test environment; either way no error.
    assert isinstance(tmpl, dict)
    for k, v in tmpl.items():
        assert isinstance(k, str)
