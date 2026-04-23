from types import SimpleNamespace

import pytest

from astrbot.core.provider.sources.gemini_embedding_source import (
    GeminiEmbeddingProvider,
)


class _FakeModelsPager:
    def __init__(self, models) -> None:
        self.page = models


class _FakeModelsAPI:
    def __init__(self, models) -> None:
        self._models = models

    async def list(self):
        return _FakeModelsPager(self._models)


class _FakeClient:
    def __init__(self, models) -> None:
        self.models = _FakeModelsAPI(models)
        self.closed = False

    async def aclose(self):
        self.closed = True


def _make_provider() -> GeminiEmbeddingProvider:
    provider_config = {
        "id": "test-gemini-embedding",
        "type": "gemini_embedding",
        "embedding_api_key": "test-key",
        "embedding_api_base": "https://generativelanguage.googleapis.com",
        "embedding_model": "gemini-embedding-exp-03-07",
    }
    return GeminiEmbeddingProvider(
        provider_config=provider_config,
        provider_settings={},
    )


@pytest.mark.asyncio
async def test_gemini_embedding_get_models_prefers_embedcontent_capability():
    provider = _make_provider()
    try:
        provider.client = _FakeClient(
            [
                SimpleNamespace(
                    name="models/gemini-2.5-flash",
                    supported_actions=["generateContent"],
                ),
                SimpleNamespace(
                    name="models/gemini-embedding-001",
                    supported_actions=["embedContent"],
                ),
                SimpleNamespace(
                    name="models/text-embedding-preview",
                    supported_generation_methods=["embedContent"],
                ),
            ]
        )
        models = await provider.get_models()
        assert models == ["gemini-embedding-001", "text-embedding-preview"]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_gemini_embedding_get_models_falls_back_to_name_matching():
    provider = _make_provider()
    try:
        provider.client = _FakeClient(
            [
                SimpleNamespace(name="models/chat-pro"),
                SimpleNamespace(name="models/embed-lite"),
                SimpleNamespace(name="models/text-embedding-preview"),
            ]
        )
        models = await provider.get_models()
        assert models == ["embed-lite", "text-embedding-preview"]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_gemini_embedding_get_models_falls_back_to_all_when_no_match():
    provider = _make_provider()
    try:
        provider.client = _FakeClient(
            [
                SimpleNamespace(name="models/gemini-2.5-pro"),
                SimpleNamespace(name="models/gemini-2.5-flash"),
                SimpleNamespace(name="models/gemini-2.5-pro"),
            ]
        )
        models = await provider.get_models()
        assert models == ["gemini-2.5-flash", "gemini-2.5-pro"]
    finally:
        await provider.terminate()
