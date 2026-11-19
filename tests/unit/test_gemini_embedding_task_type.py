"""Tests for task-aware Gemini embeddings (#11006)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest
from google.genai.errors import APIError

from astrbot.core.db.vec_db.faiss_impl.vec_db import FaissVecDB
from astrbot.core.provider.provider import EmbeddingProvider
from astrbot.core.provider.sources.gemini_embedding_source import (
    GeminiEmbeddingProvider,
)


def _make_provider(model: str) -> GeminiEmbeddingProvider:
    provider = GeminiEmbeddingProvider(
        {
            "embedding_api_key": "test-key",
            "embedding_api_base": "",
            "embedding_model": model,
        },
        {},
    )
    return provider


def _stub_embed_content(provider: GeminiEmbeddingProvider, records: list[dict]):
    """Replace the genai client call with a recorder returning dummy vectors."""

    async def fake_embed_content(**kwargs):
        records.append(kwargs)
        contents = kwargs["contents"]
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=[0.1, 0.2]) for _ in contents],
        )

    provider.client.models.embed_content = fake_embed_content


def _embedded_texts(record: dict) -> list[str]:
    return [part.text for content in record["contents"] for part in content.parts]


@pytest.mark.asyncio
async def test_query_embedding_uses_retrieval_query_task_type() -> None:
    provider = _make_provider("gemini-embedding-001")
    records: list[dict] = []
    _stub_embed_content(provider, records)

    await provider.get_query_embedding("学生优惠")

    assert len(records) == 1
    assert records[0]["config"].task_type == "RETRIEVAL_QUERY"
    assert _embedded_texts(records[0]) == ["学生优惠"]


@pytest.mark.asyncio
async def test_document_embeddings_use_retrieval_document_task_type() -> None:
    provider = _make_provider("gemini-embedding-001")
    records: list[dict] = []
    _stub_embed_content(provider, records)

    await provider.get_document_embeddings(["doc one", "doc two"])

    assert len(records) == 1
    assert records[0]["config"].task_type == "RETRIEVAL_DOCUMENT"
    assert _embedded_texts(records[0]) == ["doc one", "doc two"]


@pytest.mark.asyncio
async def test_plain_embedding_sets_no_task_type() -> None:
    provider = _make_provider("gemini-embedding-001")
    records: list[dict] = []
    _stub_embed_content(provider, records)

    await provider.get_embedding("astrbot")

    assert len(records) == 1
    assert records[0]["config"].task_type is None
    assert _embedded_texts(records[0]) == ["astrbot"]


@pytest.mark.asyncio
async def test_query_embedding_uses_task_prefix_for_embedding_v2() -> None:
    provider = _make_provider("gemini-embedding-2")
    records: list[dict] = []
    _stub_embed_content(provider, records)

    await provider.get_query_embedding("学生优惠")

    assert len(records) == 1
    # gemini-embedding-2 does not support task_type; the task goes into text.
    assert records[0]["config"].task_type is None
    assert _embedded_texts(records[0]) == ["task: search result | query: 学生优惠"]


@pytest.mark.asyncio
async def test_document_embeddings_use_document_prefix_for_embedding_v2() -> None:
    provider = _make_provider("gemini-embedding-2")
    records: list[dict] = []
    _stub_embed_content(provider, records)

    await provider.get_document_embeddings(["doc one", "doc two"])

    assert len(records) == 1
    assert records[0]["config"].task_type is None
    assert _embedded_texts(records[0]) == [
        "title: none | text: doc one",
        "title: none | text: doc two",
    ]


@pytest.mark.asyncio
async def test_plain_embedding_unprefixed_for_embedding_v2() -> None:
    provider = _make_provider("gemini-embedding-2")
    records: list[dict] = []
    _stub_embed_content(provider, records)

    await provider.get_embedding("astrbot")

    assert len(records) == 1
    assert records[0]["config"].task_type is None
    assert _embedded_texts(records[0]) == ["astrbot"]


@pytest.mark.asyncio
async def test_api_error_is_wrapped_with_context() -> None:
    provider = _make_provider("gemini-embedding-001")

    async def failing_embed_content(**kwargs):
        raise APIError(400, {"error": {"message": "bad request"}}, None)

    provider.client.models.embed_content = failing_embed_content

    with pytest.raises(Exception, match="Gemini Embedding API请求失败: bad request"):
        await provider.get_query_embedding("q")


@pytest.mark.asyncio
async def test_terminate_closes_client() -> None:
    provider = _make_provider("gemini-embedding-001")
    provider.client.aclose = AsyncMock()

    await provider.terminate()

    provider.client.aclose.assert_awaited_once()


class _RecordingProvider(EmbeddingProvider):
    """Minimal provider to verify the base-class query/document defaults."""

    def __init__(self) -> None:
        super().__init__({}, {})
        self.calls: list[tuple[str, object]] = []

    async def get_embedding(self, text: str) -> list[float]:
        self.calls.append(("single", text))
        return [1.0]

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        self.calls.append(("batch", list(text)))
        return [[1.0] for _ in text]

    def get_dim(self) -> int:
        return 1


@pytest.mark.asyncio
async def test_base_class_defaults_delegate_to_plain_methods() -> None:
    provider = _RecordingProvider()

    assert await provider.get_query_embedding("q") == [1.0]
    assert await provider.get_document_embeddings(["a", "b"]) == [[1.0], [1.0]]
    assert provider.calls == [("single", "q"), ("batch", ["a", "b"])]


def _make_vec_db() -> FaissVecDB:
    vec_db = FaissVecDB.__new__(FaissVecDB)
    vec_db.embedding_provider = AsyncMock()
    vec_db.document_storage = AsyncMock()
    vec_db.embedding_storage = AsyncMock()
    return vec_db


@pytest.mark.asyncio
async def test_vec_db_retrieve_uses_query_embedding() -> None:
    vec_db = _make_vec_db()
    vec_db.embedding_storage.search.return_value = (
        np.array([[0.5]]),
        np.array([[7]]),
    )

    await FaissVecDB.retrieve(vec_db, "query text", 3)

    vec_db.embedding_provider.get_query_embedding.assert_awaited_once_with("query text")


@pytest.mark.asyncio
async def test_vec_db_insert_uses_document_embeddings() -> None:
    vec_db = _make_vec_db()
    vec_db.embedding_provider.get_document_embeddings.return_value = [[0.1, 0.2]]
    vec_db.document_storage.insert_document.return_value = 1

    await FaissVecDB.insert(vec_db, "doc text")

    vec_db.embedding_provider.get_document_embeddings.assert_awaited_once_with(
        ["doc text"]
    )
