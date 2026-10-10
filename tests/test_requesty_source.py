from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.sources.requesty_source import ProviderRequesty


def _make_provider(overrides: dict | None = None) -> ProviderRequesty:
    config = {
        "id": "requesty-test",
        "provider": "requesty",
        "type": "requesty_chat_completion",
        "model": "openai/gpt-4o-mini",
        "key": ["test-key"],
    }
    if overrides:
        config.update(overrides)
    return ProviderRequesty(config, {})


def _page(*ids: str):
    async def _result():
        return SimpleNamespace(data=[SimpleNamespace(id=model_id) for model_id in ids])

    return _result()


def test_requesty_template_and_attribution_headers():
    templates = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]
    template = templates["Requesty"]

    assert template["provider"] == "requesty"
    assert template["type"] == "requesty_chat_completion"
    assert template["api_base"] == "https://router.requesty.ai/v1"

    provider = _make_provider({**template, "id": "requesty-test", "key": ["k"]})

    assert str(provider.client.base_url) == "https://router.requesty.ai/v1/"
    assert provider.client._custom_headers["X-Title"] == "AstrBot"
    assert (
        provider.client._custom_headers["HTTP-Referer"]
        == "https://github.com/AstrBotDevs/AstrBot"
    )


def test_requesty_provider_defaults_api_base_and_keeps_regional_base():
    assert str(_make_provider().client.base_url) == "https://router.requesty.ai/v1/"
    provider = _make_provider({"api_base": "https://router.eu.requesty.ai/v1"})
    assert str(provider.client.base_url) == "https://router.eu.requesty.ai/v1/"


@pytest.mark.asyncio
async def test_requesty_model_list_puts_managed_models_first():
    provider = _make_provider()
    provider.client.get_api_list = MagicMock(
        side_effect=[
            _page("gpt-5.4", "claude-sonnet-5", "bad\x1b[31mid"),
            _page("openai/gpt-4o-mini", "anthropic/claude-sonnet-5", "gpt-5.4"),
        ]
    )

    assert await provider.get_models() == [
        "claude-sonnet-5",
        "gpt-5.4",
        "anthropic/claude-sonnet-5",
        "openai/gpt-4o-mini",
    ]
    paths = [call.args[0] for call in provider.client.get_api_list.call_args_list]
    assert paths == ["/models/managed", "/models"]


@pytest.mark.asyncio
async def test_requesty_model_list_survives_one_failing_endpoint():
    provider = _make_provider()
    provider.client.get_api_list = MagicMock(
        side_effect=[ValueError("boom"), _page("openai/gpt-4o-mini")]
    )

    assert await provider.get_models() == ["openai/gpt-4o-mini"]


@pytest.mark.asyncio
async def test_requesty_model_list_returns_empty_when_one_endpoint_is_empty():
    provider = _make_provider()
    provider.client.get_api_list = MagicMock(side_effect=[_page(), ValueError("boom")])

    assert await provider.get_models() == []


@pytest.mark.asyncio
async def test_requesty_model_list_raises_when_all_endpoints_fail():
    provider = _make_provider()
    provider.client.get_api_list = MagicMock(side_effect=ValueError("boom"))

    with pytest.raises(Exception, match="Failed to fetch Requesty model list"):
        await provider.get_models()
