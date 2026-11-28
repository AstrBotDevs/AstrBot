"""Unit tests for concurrent multi-KB RetrievalManager execution and embedding reuse."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from astrbot.core.db.vec_db.base import Result
from astrbot.core.db.vec_db.faiss_impl.vec_db import FaissVecDB
from astrbot.core.knowledge_base.retrieval.manager import RetrievalManager


@pytest.mark.asyncio
async def test_retrieval_manager_runs_dense_and_sparse_concurrently() -> None:
    """Hybrid retrieve should await dense and sparse search concurrently."""
    dense_entered = asyncio.Event()
    sparse_entered = asyncio.Event()

    sparse_retriever = MagicMock()

    async def fake_sparse(*args, **kwargs):
        sparse_entered.set()
        await asyncio.wait_for(dense_entered.wait(), timeout=1.0)
        return []

    sparse_retriever.retrieve = fake_sparse

    rank_fusion = MagicMock()
    rank_fusion.fuse = AsyncMock(return_value=[])
    kb_db = MagicMock()
    kb_db.get_documents_with_metadata_batch = AsyncMock(return_value={})

    manager = RetrievalManager(
        sparse_retriever=sparse_retriever,
        rank_fusion=rank_fusion,
        kb_db=kb_db,
    )

    vec_db = MagicMock()

    async def fake_dense(*args, **kwargs):
        dense_entered.set()
        await asyncio.wait_for(sparse_entered.wait(), timeout=1.0)
        return []

    vec_db.retrieve = fake_dense

    kb_helper = SimpleNamespace(
        kb=SimpleNamespace(
            top_k_dense=10,
            top_k_sparse=10,
            top_m_final=5,
            rerank_provider_id=None,
        ),
        vec_db=vec_db,
    )

    results = await manager.retrieve(
        query="hello",
        kb_ids=["kb-1"],
        kb_id_helper_map={"kb-1": kb_helper},
    )

    assert results == []


@pytest.mark.asyncio
async def test_dense_retrieve_deduplicates_shared_embedding_provider_and_isolates_errors() -> (
    None
):
    """FaissVecDB instances sharing an embedding provider compute query embeddings once."""
    shared_provider = MagicMock()
    shared_provider.get_embedding = AsyncMock(return_value=[1.0, 0.0])

    failing_provider = MagicMock()
    failing_provider.get_embedding = AsyncMock(side_effect=RuntimeError("embed down"))

    def make_faiss_vec_db(provider, doc_text: str, similarity: float) -> FaissVecDB:
        vdb = FaissVecDB.__new__(FaissVecDB)
        vdb.embedding_provider = provider
        vdb.rerank_provider = None
        vdb.embedding_storage = MagicMock()
        vdb.embedding_storage.search = AsyncMock(
            return_value=(np.array([[2.0 * (1.0 - similarity)]]), np.array([[1]]))
        )
        vdb.document_storage = MagicMock()
        vdb.document_storage.get_documents = AsyncMock(
            return_value=[{"id": 1, "doc_id": f"doc-{doc_text}", "text": doc_text}]
        )
        return vdb

    vdb1 = make_faiss_vec_db(shared_provider, "kb1-hit", 0.9)
    vdb2 = make_faiss_vec_db(shared_provider, "kb2-hit", 0.95)
    vdb_bad = make_faiss_vec_db(failing_provider, "bad-hit", 0.5)

    # Also verify concurrency across vdb1 and vdb2 retrieval calls.
    in_flight = 0
    both_searching = asyncio.Event()
    orig_search_1 = vdb1.embedding_storage.search
    orig_search_2 = vdb2.embedding_storage.search

    async def barrier_search_1(*args, **kwargs):
        nonlocal in_flight
        in_flight += 1
        if in_flight == 2:
            both_searching.set()
        await asyncio.wait_for(both_searching.wait(), timeout=1.0)
        return await orig_search_1(*args, **kwargs)

    async def barrier_search_2(*args, **kwargs):
        nonlocal in_flight
        in_flight += 1
        if in_flight == 2:
            both_searching.set()
        await asyncio.wait_for(both_searching.wait(), timeout=1.0)
        return await orig_search_2(*args, **kwargs)

    vdb1.embedding_storage.search = barrier_search_1
    vdb2.embedding_storage.search = barrier_search_2

    manager = RetrievalManager(
        sparse_retriever=MagicMock(),
        rank_fusion=MagicMock(),
        kb_db=MagicMock(),
    )

    results = await manager._dense_retrieve(
        query="shared query",
        kb_ids=["kb-1", "kb-2", "kb-bad"],
        kb_options={
            "kb-1": {"vec_db": vdb1, "top_k_dense": 5},
            "kb-2": {"vec_db": vdb2, "top_k_dense": 5},
            "kb-bad": {"vec_db": vdb_bad, "top_k_dense": 5},
        },
    )

    shared_provider.get_embedding.assert_awaited_once_with("shared query")
    failing_provider.get_embedding.assert_awaited_once_with("shared query")
    assert [res.data["text"] for res in results] == ["kb2-hit", "kb1-hit"]
    assert all(isinstance(res, Result) for res in results)
