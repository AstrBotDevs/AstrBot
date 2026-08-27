from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.sources.synthorai_source import ProviderSynthorai


def _make_provider(overrides: dict | None = None) -> ProviderSynthorai:
    config = {
        "id": "synthorai-test",
        "provider": "synthorai",
        "type": "synthorai_chat_completion",
        "model": "claude-opus-5",
        "key": ["test-key"],
    }
    if overrides:
        config.update(overrides)
    return ProviderSynthorai(config, {})


def test_synthorai_template_uses_expected_defaults():
    templates = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]

    template = templates["Synthorai"]
    assert template["type"] == "synthorai_chat_completion"
    assert template["api_base"] == "https://synthorai.io/v1"
    assert template["provider_type"] == "chat_completion"


def test_synthorai_provider_sets_endpoint_and_attribution_header():
    provider = _make_provider()

    assert str(provider.client.base_url) == "https://synthorai.io/v1/"
    assert provider.client._custom_headers["X-Title"] == "AstrBot"


def test_synthorai_provider_respects_explicit_api_base():
    """A user-supplied endpoint must win over the default."""
    provider = _make_provider({"api_base": "https://example.test/v1"})

    assert str(provider.client.base_url) == "https://example.test/v1/"
