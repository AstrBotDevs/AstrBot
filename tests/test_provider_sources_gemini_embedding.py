"""Gemini embedding contracts use the real client with a mocked SDK operation."""

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from google.genai import types
from google.genai.errors import APIError

from astrbot.core.provider.sources.gemini_embedding_source import (
    GeminiEmbeddingProvider,
)


@pytest_asyncio.fixture
async def provider(monkeypatch):
    instance = GeminiEmbeddingProvider(
        {
            "embedding_api_key": "test-key",
            "embedding_api_base": "https://gemini.invalid/",
            "embedding_dimensions": 2,
        },
        {},
    )
    embed = AsyncMock(
        return_value=types.EmbedContentResponse(
            embeddings=[
                types.ContentEmbedding(values=[0.1, 0.2]),
                types.ContentEmbedding(values=[0.3, 0.4]),
            ]
        )
    )
    monkeypatch.setattr(instance.client.models, "embed_content", embed)
    try:
        yield instance, embed
    finally:
        await instance.terminate()


@pytest.mark.asyncio
async def test_single_embedding_sends_default_model_dimension_and_input(provider):
    instance, embed = provider

    assert await instance.get_embedding("first") == [0.1, 0.2]

    embed.assert_awaited_once()
    kwargs = embed.await_args.kwargs
    assert kwargs["model"] == "gemini-embedding-001"
    assert kwargs["contents"] == "first"
    assert kwargs["config"].output_dimensionality == 2
    assert instance.get_dim() == 2


@pytest.mark.asyncio
async def test_batch_embedding_preserves_text_and_vector_order(provider):
    instance, embed = provider
    instance.model = "configured-embedding-model"

    assert await instance.get_embeddings(["first", "second"]) == [
        [0.1, 0.2],
        [0.3, 0.4],
    ]

    embed.assert_awaited_once()
    kwargs = embed.await_args.kwargs
    assert kwargs["model"] == "configured-embedding-model"
    assert [content.parts[0].text for content in kwargs["contents"]] == [
        "first",
        "second",
    ]
    assert kwargs["config"].output_dimensionality == 2


@pytest.mark.asyncio
async def test_default_dimension_is_forwarded_to_the_sdk(provider):
    instance, embed = provider
    del instance.provider_config["embedding_dimensions"]

    await instance.get_embedding("first")

    assert instance.get_dim() == 768
    assert embed.await_args.kwargs["config"].output_dimensionality == 768


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method, value", [("get_embedding", "first"), ("get_embeddings", ["first"])]
)
async def test_sdk_errors_keep_their_cause_without_returning_empty_vectors(
    provider, method, value
):
    instance, embed = provider
    error = APIError(
        503, {"error": {"message": "temporarily unavailable", "status": "UNAVAILABLE"}}
    )
    embed.side_effect = error

    with pytest.raises(Exception, match="temporarily unavailable") as raised:
        await getattr(instance, method)(value)

    assert raised.value.__cause__ is error
    embed.assert_awaited_once()


@pytest.mark.asyncio
async def test_terminate_closes_the_async_sdk_client(provider, monkeypatch):
    instance, _ = provider
    close = AsyncMock(wraps=instance.client.aclose)
    monkeypatch.setattr(instance.client, "aclose", close)

    await instance.terminate()

    close.assert_awaited_once_with()
