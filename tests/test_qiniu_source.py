from types import SimpleNamespace

import pytest

from astrbot.core.provider.sources.qiniu_source import ProviderQiniu


def _make_qiniu_provider(overrides: dict | None = None) -> ProviderQiniu:
    provider_config = {
        "id": "test-qiniu",
        "type": "qiniu_chat_completion",
        "model": "deepseek-v3",
        "key": ["k"],
        "api_base": "https://api.qnaigc.com/v1",
    }
    if overrides:
        provider_config.update(overrides)
    return ProviderQiniu(
        provider_config=provider_config,
        provider_settings={},
    )


@pytest.mark.asyncio
async def test_qiniu_get_models_fallback_on_failure(monkeypatch):
    provider = _make_qiniu_provider()
    try:

        async def fail_list():
            raise RuntimeError("unavailable")

        monkeypatch.setattr(provider.client.models, "list", fail_list)
        models = await provider.get_models()
        assert models == ["deepseek-v3"]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_qiniu_get_models_fallback_when_empty(monkeypatch):
    provider = _make_qiniu_provider({"id": "test-qiniu-empty"})
    try:

        async def empty_list():
            return SimpleNamespace(data=[])

        monkeypatch.setattr(provider.client.models, "list", empty_list)
        models = await provider.get_models()
        assert models == ["deepseek-v3"]
    finally:
        await provider.terminate()
