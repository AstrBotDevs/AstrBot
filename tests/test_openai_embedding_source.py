from types import SimpleNamespace

import pytest

from astrbot.core.provider.sources.openai_embedding_source import (
    OpenAIEmbeddingProvider,
)


class _FakeModelsAPI:
    def __init__(self, model_ids: list[str]) -> None:
        self._model_ids = model_ids

    async def list(self):
        return SimpleNamespace(
            data=[SimpleNamespace(id=model_id) for model_id in self._model_ids]
        )


class _FakeClient:
    def __init__(self, model_ids: list[str]) -> None:
        self.models = _FakeModelsAPI(model_ids)
        self.closed = False

    async def close(self):
        self.closed = True


def _make_provider() -> OpenAIEmbeddingProvider:
    provider_config = {
        "id": "test-openai-embedding",
        "type": "openai_embedding",
        "embedding_api_key": "test-key",
        "embedding_api_base": "https://api.openai.com/v1",
        "embedding_model": "text-embedding-3-small",
    }
    return OpenAIEmbeddingProvider(
        provider_config=provider_config,
        provider_settings={},
    )


@pytest.mark.asyncio
async def test_openai_embedding_get_models_filters_embedding_like_ids():
    provider = _make_provider()
    try:
        provider.client = _FakeClient(
            ["gpt-4o-mini", "text-embedding-3-small", "BAAI/bge-m3"]
        )
        models = await provider.get_models()
        assert models == ["BAAI/bge-m3", "text-embedding-3-small"]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_openai_embedding_get_models_falls_back_to_all_when_no_match():
    provider = _make_provider()
    try:
        provider.client = _FakeClient(["chat-model-a", "vision-v1", "chat-model-a"])
        models = await provider.get_models()
        assert models == ["chat-model-a", "vision-v1"]
    finally:
        await provider.terminate()
