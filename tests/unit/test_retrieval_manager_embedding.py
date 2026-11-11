"""Regression tests for embedding provider resolution during dense retrieval.

Vector stores cache the embedding provider instance they were built with, so a
provider reload used to leave dense retrieval encoding queries through the
terminated instance and its pre-reload endpoint and key. Dense retrieval now
resolves the provider by ID on every call.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

# Importing the core lifecycle first resolves the import cycle between
# astrbot.core.provider.manager and astrbot.core.knowledge_base.
import astrbot.core.core_lifecycle  # noqa: F401
from astrbot.core.knowledge_base.retrieval.manager import RetrievalManager


class RecordingEmbeddingProvider:
    """Embedding provider double that records the queries it encodes."""

    def __init__(self, name: str, dim: int = 4, closed: bool = False) -> None:
        self.name = name
        self.dim = dim
        self.closed = closed
        self.queries: list[str] = []

    def get_dim(self) -> int:
        return self.dim

    async def get_embedding(self, text: str) -> list[float]:
        if self.closed:
            raise RuntimeError(
                f"[{self.name}] Cannot send a request, as the client has been closed."
            )
        self.queries.append(text)
        return [0.1] * self.dim

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        return [[0.1] * self.dim for _ in text]

    async def get_embeddings_batch(self, texts, **kwargs):
        return [[0.1] * self.dim for _ in texts]


class FakeProviderManager:
    """Provider manager double exposing the live ``inst_map`` lookup."""

    def __init__(self, providers: dict) -> None:
        self.inst_map = dict(providers)

    async def get_provider_by_id(self, provider_id: str):
        return self.inst_map.get(provider_id)


class RecordingVecDB:
    """Vector store double that reports which provider encoded the query."""

    def __init__(self, cached_provider) -> None:
        # The stale instance the store was constructed with.
        self.embedding_provider = cached_provider
        self.document_storage = MagicMock()
        self.retrieve = AsyncMock(return_value=[])
        self.seen_providers: list[str] = []

    async def _record(self, provider) -> None:
        self.seen_providers.append(provider.name)


def make_manager() -> RetrievalManager:
    kb_db = MagicMock()
    kb_db.get_documents_with_metadata_batch = AsyncMock(return_value={})

    sparse_retriever = MagicMock()
    sparse_retriever.retrieve = AsyncMock(return_value=[])

    rank_fusion = MagicMock()
    rank_fusion.fuse = AsyncMock(return_value=[])

    return RetrievalManager(
        sparse_retriever=sparse_retriever,
        rank_fusion=rank_fusion,
        kb_db=kb_db,
    )


def make_kb_helper(prov_mgr, vec_db, kb_id: str = "kb-1"):
    """Build a real KBHelper so ``get_ep()`` runs its production code path."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    helper = KBHelper.__new__(KBHelper)
    helper.kb = SimpleNamespace(
        kb_id=kb_id,
        kb_name=kb_id,
        top_k_dense=50,
        top_k_sparse=50,
        top_m_final=5,
        embedding_provider_id="embed-1",
        rerank_provider_id=None,
    )
    helper.prov_mgr = prov_mgr
    helper.vec_db = vec_db
    return helper


@pytest.mark.asyncio
async def test_dense_retrieve_uses_reloaded_embedding_provider():
    """Dense retrieval must encode the query with the current provider, not the cached one."""
    terminated = RecordingEmbeddingProvider("A", closed=True)
    reloaded = RecordingEmbeddingProvider("B")

    prov_mgr = FakeProviderManager({"embed-1": reloaded})
    vec_db = RecordingVecDB(cached_provider=terminated)
    helper = make_kb_helper(prov_mgr, vec_db)
    manager = make_manager()

    # Capture the provider that retrieve() is handed and actually encode with
    # it, so a stale instance would raise here exactly as it does in production.
    captured: list[str] = []

    async def spy_retrieve(*args, **kwargs):
        provider = kwargs.get("embedding_provider")
        if provider is None:
            provider = vec_db.embedding_provider
        captured.append(provider.name)
        await provider.get_embedding(kwargs["query"])
        return []

    vec_db.retrieve = spy_retrieve

    await manager.retrieve(
        query="query",
        kb_ids=["kb-1"],
        kb_id_helper_map={"kb-1": helper},
    )

    # The reloaded provider is used; the terminated one is never touched.
    assert captured == ["B"]
    assert terminated.queries == []
    assert reloaded.queries == ["query"]


@pytest.mark.asyncio
async def test_dense_retrieve_skips_kb_when_embedding_provider_is_unavailable():
    """A missing embedding provider degrades to no dense results, not a crash."""
    terminated = RecordingEmbeddingProvider("A", closed=True)

    prov_mgr = FakeProviderManager({})
    vec_db = RecordingVecDB(cached_provider=terminated)
    helper = make_kb_helper(prov_mgr, vec_db)
    manager = make_manager()

    results = await manager.retrieve(
        query="query",
        kb_ids=["kb-1"],
        kb_id_helper_map={"kb-1": helper},
    )

    # get_ep() raises for a missing provider; the per-KB isolation swallows it.
    vec_db.retrieve.assert_not_awaited()
    assert terminated.queries == []
    assert results == []
