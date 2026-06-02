from types import SimpleNamespace

import pytest

from astrbot.core.provider.sources.openai_embedding_source import (
    OpenAIEmbeddingProvider,
)


class FakeEmbeddingsClient:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        input_value = kwargs["input"]
        if isinstance(input_value, list):
            data = [
                SimpleNamespace(embedding=[float(index), 0.0, 1.0])
                for index, _ in enumerate(input_value)
            ]
        else:
            data = [SimpleNamespace(embedding=[1.0, 2.0, 3.0])]
        return SimpleNamespace(data=data)


@pytest.mark.asyncio
async def test_openai_embedding_does_not_send_dimensions_by_default():
    provider = OpenAIEmbeddingProvider(
        {
            "id": "openai-compatible-embedding",
            "embedding_api_key": "test-key",
            "embedding_api_base": "https://example.com/v1",
            "embedding_model": "BAAI/bge-m3",
            "embedding_dimensions": 1024,
        },
        {},
    )
    fake_embeddings = FakeEmbeddingsClient()
    provider.client = SimpleNamespace(embeddings=fake_embeddings)

    embedding = await provider.get_embedding("hello")
    embeddings = await provider.get_embeddings(["hello", "world"])

    assert embedding == [1.0, 2.0, 3.0]
    assert embeddings == [[0.0, 0.0, 1.0], [1.0, 0.0, 1.0]]
    assert provider.get_dim() == 1024
    assert fake_embeddings.calls == [
        {"input": "hello", "model": "BAAI/bge-m3"},
        {"input": ["hello", "world"], "model": "BAAI/bge-m3"},
    ]


@pytest.mark.asyncio
async def test_openai_embedding_sends_dimensions_when_explicitly_enabled():
    provider = OpenAIEmbeddingProvider(
        {
            "id": "openai-compatible-embedding",
            "embedding_api_key": "test-key",
            "embedding_api_base": "https://api.openai.com/v1",
            "embedding_model": "text-embedding-3-small",
            "embedding_dimensions": 512,
            "embedding_dimensions_as_request_param": True,
        },
        {},
    )
    fake_embeddings = FakeEmbeddingsClient()
    provider.client = SimpleNamespace(embeddings=fake_embeddings)

    embedding = await provider.get_embedding("hello")

    assert embedding == [1.0, 2.0, 3.0]
    assert provider.get_dim() == 512
    assert fake_embeddings.calls == [
        {
            "input": "hello",
            "model": "text-embedding-3-small",
            "dimensions": 512,
        },
    ]


@pytest.mark.asyncio
async def test_openai_embedding_omits_dimensions_when_dimension_not_configured():
    provider = OpenAIEmbeddingProvider(
        {
            "id": "openai-compatible-embedding",
            "embedding_api_key": "test-key",
            "embedding_api_base": "https://example.com/v1",
            "embedding_model": "BAAI/bge-m3",
            "embedding_dimensions_as_request_param": True,
        },
        {},
    )
    fake_embeddings = FakeEmbeddingsClient()
    provider.client = SimpleNamespace(embeddings=fake_embeddings)

    embeddings = await provider.get_embeddings(["hello", "world"])

    assert embeddings == [[0.0, 0.0, 1.0], [1.0, 0.0, 1.0]]
    assert provider.get_dim() == 0
    assert fake_embeddings.calls == [
        {"input": ["hello", "world"], "model": "BAAI/bge-m3"},
    ]
