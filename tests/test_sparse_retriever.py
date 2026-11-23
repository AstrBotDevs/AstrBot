"""Sparse retrieval carries stored document identities through real FTS queries."""

from types import SimpleNamespace

import pytest

from astrbot.core.db.vec_db.faiss_impl.document_storage import DocumentStorage
from astrbot.core.knowledge_base.retrieval.sparse_retriever import SparseRetriever


@pytest.mark.asyncio
async def test_real_fts_result_preserves_document_and_chunk_identity(tmp_path):
    storage = DocumentStorage(str(tmp_path / "documents.db"))
    try:
        await storage.initialize()
        await storage.insert_documents_batch(
            doc_ids=["chunk-a", "chunk-b"],
            texts=["orchard apple harvest", "unrelated ocean sailing"],
            metadatas=[
                {"kb_id": "kb-1", "kb_doc_id": "manual-a", "chunk_index": 7},
                {"kb_id": "kb-1", "kb_doc_id": "manual-b", "chunk_index": 2},
            ],
        )
        retriever = SparseRetriever(kb_db=None)
        results = await retriever.retrieve(
            "apple",
            ["missing", "kb-1"],
            {
                "kb-1": {
                    "vec_db": SimpleNamespace(document_storage=storage),
                    "top_k_sparse": 1,
                }
            },
        )

        assert [
            (item.chunk_id, item.doc_id, item.kb_id, item.chunk_index)
            for item in results
        ] == [("chunk-a", "manual-a", "kb-1", 7)]
        assert results[0].content == "orchard apple harvest"
        assert results[0].rank == 1
        assert results[0].score > 0
    finally:
        await storage.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "options", [{}, {"kb": None}, {"kb": {}}, {"kb": {"vec_db": None}}]
)
async def test_missing_vector_stores_produce_no_sparse_results(options):
    assert await SparseRetriever(kb_db=None).retrieve("apple", ["kb"], options) == []
