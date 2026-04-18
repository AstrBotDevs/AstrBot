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
