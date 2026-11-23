"""Embedding requests use the real SDK and an in-memory HTTP transport."""

import json

import httpx
import pytest
from openai import AsyncOpenAI, AuthenticationError

from astrbot.core.provider.sources.openai_embedding_source import (
    OpenAIEmbeddingProvider,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("texts", "method", "expected"),
    [
        ("first", "get_embedding", [0.1, 0.2]),
        (["first", "second"], "get_embeddings", [[0.1, 0.2], [0.3, 0.4]]),
    ],
)
async def test_embedding_requests_preserve_input_model_and_vectors(
    texts, method, expected
):
    requests = []

    def handle(request):
        requests.append(request)
        inputs = json.loads(request.content)["input"]
        count = 1 if isinstance(inputs, str) else len(inputs)
        return httpx.Response(
            200,
            json={
                "object": "list",
                "model": "text-embedding-3-small",
                "data": [
                    {"object": "embedding", "index": i, "embedding": vector}
                    for i, vector in enumerate([[0.1, 0.2], [0.3, 0.4]][:count])
                ],
                "usage": {"prompt_tokens": count, "total_tokens": count},
            },
        )

    provider = OpenAIEmbeddingProvider(
        {
            "embedding_api_key": "test-key",
            "embedding_api_base": "https://embedding.invalid",
            "embedding_dimensions": 2,
            "embedding_dimensions_mode": "always",
        },
        {},
    )
    assert str(provider.client.base_url) == "https://embedding.invalid/v1/"
    await provider.client.close()
    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    provider.client = AsyncOpenAI(
        api_key="test-key", base_url="https://embedding.invalid/v1", http_client=client
    )
    try:
        assert await getattr(provider, method)(texts) == expected
        assert provider.get_dim() == 2
        assert len(requests) == 1
        assert requests[0].url.path == "/v1/embeddings"
        assert requests[0].headers["Authorization"] == "Bearer test-key"
        assert json.loads(requests[0].content) == {
            "input": texts,
            "model": "text-embedding-3-small",
            "dimensions": 2,
            "encoding_format": "base64",
        }
    finally:
        await provider.terminate()
    assert client.is_closed


@pytest.mark.asyncio
async def test_embedding_authentication_errors_propagate_and_client_is_closed():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(401, json={"error": {"message": "invalid credential"}})

    provider = OpenAIEmbeddingProvider({"embedding_api_key": "test-key"}, {})
    await provider.client.close()
    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    provider.client = AsyncOpenAI(
        api_key="test-key", base_url="https://embedding.invalid/v1", http_client=client
    )
    try:
        with pytest.raises(AuthenticationError, match="invalid credential"):
            await provider.get_embedding("input")
        assert len(requests) == 1
    finally:
        await provider.terminate()
    assert client.is_closed
