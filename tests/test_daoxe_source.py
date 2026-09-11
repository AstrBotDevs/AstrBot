from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.sources.daoxe_source import ProviderDaoXE


def _make_provider(overrides: dict | None = None) -> ProviderDaoXE:
    config = {
        "id": "daoxe-test",
        "provider": "daoxe",
        "type": "daoxe_chat_completion",
        "model": "test-model",
        "key": ["test-key"],
    }
    if overrides:
        config.update(overrides)
    return ProviderDaoXE(config, {})


def test_daoxe_template_uses_expected_defaults():
    templates = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]

    template = templates["DaoXE"]
    assert template["type"] == "daoxe_chat_completion"
    assert template["api_base"] == "https://api.daoxe.com/v1"
    assert template["custom_headers"] == {}


def test_daoxe_provider_sets_default_endpoint():
    provider = _make_provider()

    assert str(provider.client.base_url) == "https://api.daoxe.com/v1/"


def test_daoxe_provider_keeps_custom_endpoint():
    provider = _make_provider({"api_base": "https://my-clone.example.com/v1"})

    assert str(provider.client.base_url) == "https://my-clone.example.com/v1/"


@pytest.mark.asyncio
async def test_daoxe_model_list_returns_sorted_ids():
    provider = _make_provider()

    provider.client.models.list = AsyncMock(
        return_value=SimpleNamespace(
            data=[
                SimpleNamespace(id="z-model"),
                SimpleNamespace(id="a-model"),
            ]
        )
    )

    assert await provider.get_models() == ["a-model", "z-model"]


@pytest.mark.asyncio
async def test_daoxe_model_list_raises_on_failure():
    provider = _make_provider()

    provider.client.models.list = AsyncMock(
        side_effect=RuntimeError("boom")
    )

    with pytest.raises(Exception, match="Failed to fetch DaoXE model list"):
        await provider.get_models()
