import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.provider.sources.openai_embedding_source import (
    OpenAIEmbeddingProvider,
)


def _make_provider() -> OpenAIEmbeddingProvider:
    provider = OpenAIEmbeddingProvider(
        provider_config={
            "id": "test-openai-embedding",
            "type": "openai_embedding",
            "embedding_api_key": "test-key",
            "embedding_api_base": "https://api.openai.com/v1",
            "embedding_model": "text-embedding-3-large",
            "embedding_dimensions": 3,
        },
        provider_settings={},
    )
    provider.client = SimpleNamespace(
        embeddings=SimpleNamespace(create=AsyncMock()),
        close=AsyncMock(),
    )
    return provider


@pytest.mark.asyncio
async def test_get_embedding_accepts_sdk_object_response():
    provider = _make_provider()
    provider.client.embeddings.create.return_value = SimpleNamespace(
        data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])]
    )

    try:
        result = await provider.get_embedding("astrbot")
        assert result == [0.1, 0.2, 0.3]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_get_embeddings_accepts_json_string_response():
    provider = _make_provider()
    provider.client.embeddings.create.return_value = json.dumps(
        {
            "data": [
                {"embedding": [0.1, 0.2, 0.3]},
                {"embedding": [1, 2, 3]},
            ]
        }
    )

    try:
        result = await provider.get_embeddings(["a", "b"])
        assert result == [[0.1, 0.2, 0.3], [1.0, 2.0, 3.0]]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_get_embedding_rejects_empty_vectors():
    provider = _make_provider()
    provider.client.embeddings.create.return_value = {"data": []}

    try:
        with pytest.raises(
            ValueError, match="Embedding response did not include any vectors"
        ):
            await provider.get_embedding("astrbot")
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_get_embedding_rejects_none_response():
    provider = _make_provider()
    provider.client.embeddings.create.return_value = None

    try:
        with pytest.raises(TypeError, match="Unexpected embedding response type"):
            await provider.get_embedding("astrbot")
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_get_embeddings_rejects_none_item():
    provider = _make_provider()
    provider.client.embeddings.create.return_value = {"data": [None]}

    try:
        with pytest.raises(TypeError, match="Unexpected embedding item type"):
            await provider.get_embeddings(["astrbot"])
    finally:
        await provider.terminate()
