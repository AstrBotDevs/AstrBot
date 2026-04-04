import pytest

from astrbot.core.provider.register import provider_cls_map
from astrbot.core.provider.sources.longcat_source import ProviderLongCat


def _make_provider(overrides: dict | None = None) -> ProviderLongCat:
    provider_config = {
        "id": "test-longcat",
        "type": "longcat_chat_completion",
        "key": ["test-key"],
        "model": "LongCat-Flash-Chat",
        "api_base": "",
    }
    if overrides:
        provider_config.update(overrides)

    return ProviderLongCat(provider_config=provider_config, provider_settings={})


def test_longcat_provider_is_registered():
    assert "longcat_chat_completion" in provider_cls_map
    assert provider_cls_map["longcat_chat_completion"].cls_type is ProviderLongCat


@pytest.mark.asyncio
async def test_longcat_api_base_defaults_to_v1():
    provider = _make_provider()
    try:
        assert provider.provider_config["api_base"] == "https://api.longcat.chat/openai/v1"
        assert provider.get_model() == "LongCat-Flash-Chat"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_longcat_api_base_normalizes_openai_path():
    provider = _make_provider({"api_base": "https://api.longcat.chat/openai"})
    try:
        assert provider.provider_config["api_base"] == "https://api.longcat.chat/openai/v1"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_longcat_api_base_keeps_v1_path():
    provider = _make_provider({"api_base": "https://api.longcat.chat/openai/v1"})
    try:
        assert provider.provider_config["api_base"] == "https://api.longcat.chat/openai/v1"
    finally:
        await provider.terminate()
