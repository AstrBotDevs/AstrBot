import json
from types import SimpleNamespace

import pytest

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


@pytest.mark.asyncio
async def test_sparse_retriever_uses_fts5_when_available():
    storage = FTSStorage()
    vec_db = SimpleNamespace(document_storage=storage)
    retriever = SparseRetriever(kb_db=None)

    results = await retriever.retrieve(
        query="apple",
        kb_ids=["kb-1"],
        kb_options={"kb-1": {"vec_db": vec_db, "top_k_sparse": 1}},
    )

    assert [result.chunk_id for result in results] == ["chunk-1"]
    assert storage.search_sparse_calls == 1
    assert storage.get_documents_calls == 0


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


class MultiKBStorage:
    """模拟多知识库 BM25 回退场景"""

    def __init__(self, kb_id: str):
        self.kb_id = kb_id
        self.search_sparse_calls = 0
        self.get_documents_calls = 0

    async def search_sparse(self, query_tokens: list[str], limit: int):
        self.search_sparse_calls += 1
        return None  # 始终回退到 BM25

    async def get_documents(self, metadata_filters: dict, limit: int | None, offset):
        self.get_documents_calls += 1
        # 返回 10 条 chunk，远多于 top_k_sparse 限制
        return [
            make_doc(f"{self.kb_id}-chunk-{i}", f"document chunk {i}", i)
            for i in range(10)
        ]


@pytest.mark.asyncio
async def test_bm25_fallback_respects_per_kb_top_k_sparse():
    """多知识库 BM25 回退时，每个知识库的结果应被截断到各自的 top_k_sparse

    Phase 1C: 验证 top_k_sparse 不再被错误求和，而是逐 KB 截断。
    """
    storage_a = MultiKBStorage("kb-a")
    storage_b = MultiKBStorage("kb-b")
    vec_db_a = SimpleNamespace(document_storage=storage_a)
    vec_db_b = SimpleNamespace(document_storage=storage_b)
    retriever = SparseRetriever(kb_db=None)

    results = await retriever.retrieve(
        query="test query",
        kb_ids=["kb-a", "kb-b"],
        kb_options={
            "kb-a": {"vec_db": vec_db_a, "top_k_sparse": 2},
            "kb-b": {"vec_db": vec_db_b, "top_k_sparse": 3},
        },
    )

    # 总结果数不应超过 max(2, 3) = 3（最终截断），且每个 KB 各贡献 ≤ 其 top_k
    assert len(results) <= 3, f"结果过多: {len(results)}"
    kb_a_count = sum(1 for r in results if r.kb_id == "kb-a")
    kb_b_count = sum(1 for r in results if r.kb_id == "kb-b")
    assert kb_a_count <= 2, f"KB-A 贡献了 {kb_a_count} 条，应 ≤ 2"
    assert kb_b_count <= 3, f"KB-B 贡献了 {kb_b_count} 条，应 ≤ 3"
