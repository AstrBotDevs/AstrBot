import asyncio
import importlib
import json
import sys
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from astrbot.core.db.vec_db.base import Result
from astrbot.core.db.vec_db.faiss_impl.vec_db import FaissVecDB
from astrbot.core.knowledge_base.retrieval import sparse_retriever
from astrbot.core.knowledge_base.retrieval.manager import RetrievalManager
from astrbot.core.knowledge_base.retrieval.sparse_retriever import SparseRetriever


def make_doc(
    chunk_id: str,
    text: str,
    chunk_index: int = 0,
    kb_id: str = "kb-1",
) -> dict:
    return {
        "doc_id": chunk_id,
        "text": text,
        "metadata": json.dumps(
            {
                "chunk_index": chunk_index,
                "kb_doc_id": f"doc-{chunk_index}",
                "kb_id": kb_id,
            },
        ),
    }


class FTSStorage:
    def __init__(self):
        self.search_sparse_calls = 0
        self.get_documents_calls = 0

    async def search_sparse(self, query_tokens: list[str], limit: int):
        self.search_sparse_calls += 1
        assert query_tokens == ["apple"]
        assert limit == 1
        return [
            {
                **make_doc("chunk-1", "apple banana", 0),
                "score": -1.0,
            },
        ]

    async def get_documents(self, *args, **kwargs):
        self.get_documents_calls += 1
        return []


class FallbackStorage:
    def __init__(self):
        self.search_sparse_calls = 0
        self.get_documents_calls = 0

    async def search_sparse(self, query_tokens: list[str], limit: int):
        self.search_sparse_calls += 1
        return None

    async def get_documents(self, metadata_filters: dict, limit: int | None, offset):
        self.get_documents_calls += 1
        return [
            make_doc("chunk-1", "apple banana", 0),
            make_doc("chunk-2", "orange pear", 1),
            make_doc("chunk-3", "grape melon", 2),
        ]


class StaticFTSStorage:
    def __init__(self, documents: list[dict]):
        self.documents = documents

    async def search_sparse(self, query_tokens: list[str], limit: int):
        return self.documents[:limit]


@pytest.mark.asyncio
async def test_sparse_retriever_uses_fts5_without_importing_bm25(monkeypatch):
    storage = FTSStorage()
    vec_db = SimpleNamespace(document_storage=storage)
    retriever = SparseRetriever(kb_db=None)
    monkeypatch.setitem(sys.modules, "rank_bm25", None)

    results = await retriever.retrieve(
        query="apple",
        kb_ids=["kb-1"],
        kb_options={"kb-1": {"vec_db": vec_db, "top_k_sparse": 1}},
    )

    assert [result.chunk_id for result in results] == ["chunk-1"]
    assert storage.search_sparse_calls == 1
    assert storage.get_documents_calls == 0


def test_sparse_retriever_module_import_does_not_load_bm25(monkeypatch):
    monkeypatch.setitem(sys.modules, "rank_bm25", None)

    importlib.reload(sparse_retriever)


@pytest.mark.asyncio
async def test_sparse_retriever_falls_back_to_bm25_when_fts5_is_unavailable():
    storage = FallbackStorage()
    vec_db = SimpleNamespace(document_storage=storage)
    retriever = SparseRetriever(kb_db=None)

    results = await retriever.retrieve(
        query="apple",
        kb_ids=["kb-1"],
        kb_options={"kb-1": {"vec_db": vec_db, "top_k_sparse": 1}},
    )

    assert [result.chunk_id for result in results] == ["chunk-1"]
    assert storage.search_sparse_calls == 1
    assert storage.get_documents_calls == 1


@pytest.mark.asyncio
async def test_sparse_retriever_preserves_per_kb_fts_ranks():
    large_storage = StaticFTSStorage(
        [
            {
                **make_doc("large-1", "管理员账号安全说明", 0, "kb-large"),
                "score": -12.0,
            },
            {
                **make_doc("large-2", "密码策略说明", 1, "kb-large"),
                "score": -10.0,
            },
        ],
    )
    small_storage = StaticFTSStorage(
        [
            {
                **make_doc(
                    "small-exact",
                    "如何重置管理员密码？",
                    0,
                    "kb-small",
                ),
                "score": -0.00001,
            },
        ],
    )
    retriever = SparseRetriever(kb_db=None)

    results = await retriever.retrieve(
        query="如何重置管理员密码？",
        kb_ids=["kb-large", "kb-small"],
        kb_options={
            "kb-large": {
                "vec_db": SimpleNamespace(document_storage=large_storage),
                "top_k_sparse": 2,
            },
            "kb-small": {
                "vec_db": SimpleNamespace(document_storage=small_storage),
                "top_k_sparse": 1,
            },
        },
    )

    ranks = {result.chunk_id: result.rank for result in results}
    assert ranks == {"large-1": 1, "large-2": 2, "small-exact": 1}


@pytest.mark.asyncio
async def test_sparse_retriever_queries_multiple_kbs_concurrently():
    """Multiple KB FTS searches should run concurrently rather than sequentially."""
    both_entered = asyncio.Event()
    in_flight = 0

    class BarrierFTSStorage:
        def __init__(self, doc_id: str, kb_id: str):
            self.doc_id = doc_id
            self.kb_id = kb_id

        async def search_sparse(self, query_tokens: list[str], limit: int):
            nonlocal in_flight
            in_flight += 1
            if in_flight == 2:
                both_entered.set()
            await asyncio.wait_for(both_entered.wait(), timeout=1.0)
            in_flight -= 1
            return [{**make_doc(self.doc_id, "apple", 0, self.kb_id), "score": -1.0}]

    retriever = SparseRetriever(kb_db=None)
    results = await retriever.retrieve(
        query="apple",
        kb_ids=["kb-1", "kb-2"],
        kb_options={
            "kb-1": {
                "vec_db": SimpleNamespace(
                    document_storage=BarrierFTSStorage("c1", "kb-1")
                ),
                "top_k_sparse": 5,
            },
            "kb-2": {
                "vec_db": SimpleNamespace(
                    document_storage=BarrierFTSStorage("c2", "kb-2")
                ),
                "top_k_sparse": 5,
            },
        },
    )

    assert {result.chunk_id for result in results} == {"c1", "c2"}


@pytest.mark.asyncio
async def test_sparse_retriever_bm25_fallback_runs_off_event_loop_thread(monkeypatch):
    """BM25 tokenization and scoring must run in a worker thread via to_thread."""
    main_thread_id = threading.get_ident()
    scoring_thread_ids: list[int] = []
    orig_score = sparse_retriever._score_bm25_chunks

    def spy_score(query, chunks, stopwords, top_k_sparse):
        scoring_thread_ids.append(threading.get_ident())
        return orig_score(query, chunks, stopwords, top_k_sparse)

    monkeypatch.setattr(sparse_retriever, "_score_bm25_chunks", spy_score)

    storage = FallbackStorage()
    retriever = SparseRetriever(kb_db=None)
    results = await retriever.retrieve(
        query="apple",
        kb_ids=["kb-1"],
        kb_options={
            "kb-1": {
                "vec_db": SimpleNamespace(document_storage=storage),
                "top_k_sparse": 1,
            }
        },
    )

    assert [result.chunk_id for result in results] == ["chunk-1"]
    assert len(scoring_thread_ids) == 1
    assert scoring_thread_ids[0] != main_thread_id


@pytest.mark.asyncio
async def test_sparse_retriever_isolates_failing_kbs_in_fts_and_bm25_fallback():
    """Failing FTS or BM25 fallback KBs should not abort successful sibling KBs."""

    class FailingFTSStorage:
        async def search_sparse(self, query_tokens: list[str], limit: int):
            raise RuntimeError("fts unavailable")

    class FailingBM25Storage:
        async def search_sparse(self, query_tokens: list[str], limit: int):
            return None

        async def get_documents(self, metadata_filters, limit=None, offset=None):
            raise RuntimeError("db unavailable")

    retriever = SparseRetriever(kb_db=None)
    results = await retriever.retrieve(
        query="apple",
        kb_ids=["kb-fts-bad", "kb-bm25-bad", "kb-good-fts", "kb-good-bm25"],
        kb_options={
            "kb-fts-bad": {
                "vec_db": SimpleNamespace(document_storage=FailingFTSStorage()),
                "top_k_sparse": 5,
            },
            "kb-bm25-bad": {
                "vec_db": SimpleNamespace(document_storage=FailingBM25Storage()),
                "top_k_sparse": 5,
            },
            "kb-good-fts": {
                "vec_db": SimpleNamespace(document_storage=FTSStorage()),
                "top_k_sparse": 1,
            },
            "kb-good-bm25": {
                "vec_db": SimpleNamespace(document_storage=FallbackStorage()),
                "top_k_sparse": 1,
            },
        },
    )

    assert {result.kb_id for result in results} == {"kb-good-fts", "kb-good-bm25"}


@pytest.mark.asyncio
async def test_retrieval_manager_runs_dense_and_sparse_concurrently():
    """Hybrid retrieve should await dense and sparse search concurrently."""
    dense_entered = asyncio.Event()
    sparse_entered = asyncio.Event()

    sparse_stub = MagicMock()

    async def fake_sparse(*args, **kwargs):
        sparse_entered.set()
        await asyncio.wait_for(dense_entered.wait(), timeout=1.0)
        return []

    sparse_stub.retrieve = fake_sparse

    rank_fusion = MagicMock()
    rank_fusion.fuse = AsyncMock(return_value=[])
    kb_db = MagicMock()
    kb_db.get_documents_with_metadata_batch = AsyncMock(return_value={})

    manager = RetrievalManager(
        sparse_retriever=sparse_stub,
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
async def test_retrieval_manager_cancels_sibling_branch_on_failure():
    """Failure in sparse or dense retrieval cancels the sibling branch immediately."""
    dense_cancelled = asyncio.Event()
    dense_started = asyncio.Event()

    sparse_stub = MagicMock()

    async def failing_sparse(*args, **kwargs):
        await asyncio.wait_for(dense_started.wait(), timeout=1.0)
        raise RuntimeError("sparse boom")

    sparse_stub.retrieve = failing_sparse

    manager = RetrievalManager(
        sparse_retriever=sparse_stub,
        rank_fusion=MagicMock(),
        kb_db=MagicMock(),
    )

    async def hanging_dense(*args, **kwargs):
        dense_started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            dense_cancelled.set()
            raise

    manager._dense_retrieve = hanging_dense
    kb_helper = SimpleNamespace(
        kb=SimpleNamespace(
            top_k_dense=10,
            top_k_sparse=10,
            top_m_final=5,
            rerank_provider_id=None,
        ),
        vec_db=MagicMock(),
    )

    with pytest.raises(RuntimeError, match="sparse boom"):
        await manager.retrieve(
            query="hello",
            kb_ids=["kb-1"],
            kb_id_helper_map={"kb-1": kb_helper},
        )
    assert dense_cancelled.is_set()


@pytest.mark.asyncio
async def test_dense_retrieve_deduplicates_embedding_and_handles_legacy_subclass():
    """Shared embedding providers compute once; legacy subclasses without query_embedding work."""
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

    class LegacyFaissSubclass(FaissVecDB):
        async def retrieve(
            self,
            query: str,
            k: int = 5,
            rerank: bool = False,
            fetch_k: int = 20,
            metadata_filters: dict | None = None,
        ) -> list[Result]:
            return [Result(similarity=0.88, data={"text": "legacy-hit"})]

    vdb1 = make_faiss_vec_db(shared_provider, "kb1-hit", 0.9)
    vdb2 = make_faiss_vec_db(shared_provider, "kb2-hit", 0.95)
    vdb_bad = make_faiss_vec_db(failing_provider, "bad-hit", 0.5)
    vdb_legacy = LegacyFaissSubclass.__new__(LegacyFaissSubclass)
    vdb_legacy.embedding_provider = shared_provider
    vdb_legacy.rerank_provider = None

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
        kb_ids=["kb-1", "kb-2", "kb-bad", "kb-legacy"],
        kb_options={
            "kb-1": {"vec_db": vdb1, "top_k_dense": 5},
            "kb-2": {"vec_db": vdb2, "top_k_dense": 5},
            "kb-bad": {"vec_db": vdb_bad, "top_k_dense": 5},
            "kb-legacy": {"vec_db": vdb_legacy, "top_k_dense": 5},
        },
    )

    shared_provider.get_embedding.assert_awaited_once_with("shared query")
    failing_provider.get_embedding.assert_awaited_once_with("shared query")
    assert [res.data["text"] for res in results] == [
        "kb2-hit",
        "kb1-hit",
        "legacy-hit",
    ]
    assert all(isinstance(res, Result) for res in results)
