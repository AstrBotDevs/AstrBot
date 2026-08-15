from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.sources.ssycloud_source import ProviderSSYCloud


def _make_provider(overrides: dict | None = None) -> ProviderSSYCloud:
    config = {
        "id": "ssycloud-test",
        "provider": "ssycloud",
        "type": "ssycloud_chat_completion",
        "model": "test-model",
        "key": ["test-key"],
    }
    if overrides:
        config.update(overrides)
    return ProviderSSYCloud(config, {})


def test_ssycloud_template_uses_expected_defaults():
    templates = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]
    template = templates["SSYCloud(胜算云)"]
    assert template["type"] == "ssycloud_chat_completion"
    assert template["api_base"] == "https://router.shengsuanyun.com/api/v1"
    assert template["custom_headers"] == {"X-Title": "AstrBot"}


def test_ssycloud_provider_sets_endpoint_and_header():
    provider = _make_provider()
    assert str(provider.client.base_url) == "https://router.shengsuanyun.com/api/v1/"
    assert provider.client._custom_headers["X-Title"] == "AstrBot"


def test_ssycloud_provider_preserves_custom_header():
    provider = _make_provider({"custom_headers": {"X-Title": "Custom Client"}})
    assert provider.client._custom_headers["X-Title"] == "Custom Client"


@pytest.mark.asyncio
async def test_ssycloud_model_list_filters_non_chat_models():
    provider = _make_provider()
    provider.client.models.list = AsyncMock(
        return_value=SimpleNamespace(
            data=[
                SimpleNamespace(
                    id="chat-model",
                    support_apis=["/v1/chat/completions", "/v1/messages"],
                ),
                SimpleNamespace(id="responses-model", support_apis=["/v1/responses"]),
                SimpleNamespace(
                    id="extra-chat-model",
                    model_extra={"support_apis": ["/v1/chat/completions"]},
                ),
                SimpleNamespace(id="legacy-model"),
            ]
        )
    )
    assert await provider.get_models() == [
        "chat-model",
        "extra-chat-model",
        "legacy-model",
    ]
