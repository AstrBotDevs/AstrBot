import importlib
import json
import sys
from types import SimpleNamespace

import pytest

from astrbot.core.knowledge_base.retrieval import sparse_retriever
from astrbot.core.knowledge_base.retrieval.sparse_retriever import SparseRetriever


def make_doc(chunk_id: str, text: str, chunk_index: int = 0) -> dict:
    return {
        "doc_id": chunk_id,
        "text": text,
        "metadata": json.dumps(
            {
                "chunk_index": chunk_index,
                "kb_doc_id": f"doc-{chunk_index}",
                "kb_id": "kb-1",
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
    def __init__(self, documents: list[dict]) -> None:
        self.documents = documents

    async def search_sparse(self, query_tokens: list[str], limit: int):
        del query_tokens
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
    """FTS-only deployments do not need rank_bm25 during module import."""
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
    """Independent FTS scores use per-knowledge-base ranks for later RRF."""
    large_storage = StaticFTSStorage(
        [
            {**make_doc("large-1", "admin account", 0), "score": -12.0},
            {**make_doc("large-2", "password policy", 1), "score": -10.0},
        ]
    )
    small_storage = StaticFTSStorage(
        [{**make_doc("small-exact", "reset admin password", 0), "score": -0.01}]
    )
    retriever = SparseRetriever(kb_db=None)

    results = await retriever.retrieve(
        query="reset admin password",
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

    assert {result.chunk_id: result.rank for result in results} == {
        "large-1": 1,
        "large-2": 2,
        "small-exact": 1,
    }


class CountingFallbackStorage:
    def __init__(self, documents: list[dict]) -> None:
        self.documents = documents
        self.search_sparse_calls = 0
        self.get_documents_calls = 0

    async def search_sparse(self, query_tokens: list[str], limit: int):
        del query_tokens, limit
        self.search_sparse_calls += 1
        return None

    async def get_documents(self, metadata_filters: dict, limit: int | None, offset):
        del metadata_filters, limit, offset
        self.get_documents_calls += 1
        return self.documents


def _fallback_vec_db(
    documents: list[dict],
) -> tuple[SimpleNamespace, CountingFallbackStorage]:
    storage = CountingFallbackStorage(documents)
    return SimpleNamespace(document_storage=storage), storage


@pytest.mark.asyncio
async def test_bm25_fallback_keeps_per_kb_top_k_and_ranks():
    kb_a_db, _ = _fallback_vec_db(
        [
            make_doc("a-1", "apple apple apple", 0),
            make_doc("a-2", "apple fruit", 1),
            make_doc("a-3", "unrelated zebra", 2),
        ]
    )
    kb_b_db, _ = _fallback_vec_db(
        [
            make_doc("b-1", "apple pie", 0),
            make_doc("b-2", "banana boat", 1),
            make_doc("b-3", "carrot cake", 2),
        ]
    )
    retriever = SparseRetriever(kb_db=None)

    results = await retriever.retrieve(
        query="apple",
        kb_ids=["kb-a", "kb-b"],
        kb_options={
            "kb-a": {"vec_db": kb_a_db, "top_k_sparse": 2},
            "kb-b": {"vec_db": kb_b_db, "top_k_sparse": 1},
        },
    )

    assert len(results) == 3
    a_ranks = [result.rank for result in results if result.kb_id == "kb-a"]
    b_ranks = [result.rank for result in results if result.kb_id == "kb-b"]
    assert sorted(a_ranks) == [1, 2]
    assert b_ranks == [1]


@pytest.mark.asyncio
async def test_bm25_fallback_reuses_cached_index_per_kb():
    kb_a_db, storage_a = _fallback_vec_db([make_doc("a-1", "apple banana", 0)])
    kb_b_db, storage_b = _fallback_vec_db([make_doc("b-1", "apple pie", 0)])
    retriever = SparseRetriever(kb_db=None)
    options = {
        "kb-a": {"vec_db": kb_a_db, "top_k_sparse": 1},
        "kb-b": {"vec_db": kb_b_db, "top_k_sparse": 1},
    }

    await retriever.retrieve(query="apple", kb_ids=["kb-a", "kb-b"], kb_options=options)
    await retriever.retrieve(query="apple", kb_ids=["kb-a", "kb-b"], kb_options=options)

    assert storage_a.get_documents_calls == 1
    assert storage_b.get_documents_calls == 1


@pytest.mark.asyncio
async def test_bm25_fallback_invalidate_rebuilds_only_that_kb():
    kb_a_db, storage_a = _fallback_vec_db([make_doc("a-1", "apple banana", 0)])
    kb_b_db, storage_b = _fallback_vec_db([make_doc("b-1", "apple pie", 0)])
    retriever = SparseRetriever(kb_db=None)
    options = {
        "kb-a": {"vec_db": kb_a_db, "top_k_sparse": 1},
        "kb-b": {"vec_db": kb_b_db, "top_k_sparse": 1},
    }

    await retriever.retrieve(query="apple", kb_ids=["kb-a", "kb-b"], kb_options=options)
    retriever.invalidate("kb-a")
    await retriever.retrieve(query="apple", kb_ids=["kb-a", "kb-b"], kb_options=options)

    assert storage_a.get_documents_calls == 2
    assert storage_b.get_documents_calls == 1
