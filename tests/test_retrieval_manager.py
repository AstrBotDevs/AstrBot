"""Retrieval coordinates vector search, sparse search, metadata, and reranking."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.knowledge_base.models import KnowledgeBase
from astrbot.core.knowledge_base.retrieval.manager import RetrievalManager
from astrbot.core.knowledge_base.retrieval.rank_fusion import FusedResult


@pytest.fixture
def retrieval():
    fused = [
        FusedResult("chunk-a", 2, "doc-a", "kb-1", "first answer", 0.9),
        FusedResult("chunk-b", 3, "doc-b", "kb-1", "second answer", 0.5),
    ]
    database = SimpleNamespace(
        get_documents_with_metadata_batch=AsyncMock(
            return_value={
                identifier: {
                    "document": SimpleNamespace(doc_name=f"{identifier}.md"),
                    "knowledge_base": SimpleNamespace(kb_name="manual"),
                }
                for identifier in ("doc-a", "doc-b")
            }
        )
    )
    sparse = SimpleNamespace(retrieve=AsyncMock(return_value=[]))
    fusion = SimpleNamespace(fuse=AsyncMock(return_value=fused))
    vector = SimpleNamespace(retrieve=AsyncMock(return_value=[]), rerank_provider=None)
    helper = SimpleNamespace(
        kb=KnowledgeBase(kb_id="kb-1", kb_name="manual", top_k_dense=4, top_k_sparse=3),
        vec_db=vector,
    )
    manager = RetrievalManager(sparse, fusion, database)
    return SimpleNamespace(
        manager=manager,
        helper=helper,
        database=database,
        sparse=sparse,
        fusion=fusion,
        vector=vector,
    )


@pytest.mark.asyncio
async def test_empty_selection_does_not_touch_backends(retrieval):
    assert await retrieval.manager.retrieve("question", [], {}) == []
    retrieval.vector.retrieve.assert_not_awaited()
    retrieval.sparse.retrieve.assert_not_awaited()
    retrieval.fusion.fuse.assert_not_awaited()
    retrieval.database.get_documents_with_metadata_batch.assert_not_awaited()


@pytest.mark.asyncio
async def test_retrieval_passes_limits_and_enriches_result_metadata(retrieval):
    results = await retrieval.manager.retrieve(
        "question",
        ["missing", "kb-1"],
        {"kb-1": retrieval.helper},
        top_k_fusion=7,
        top_m_final=1,
    )

    retrieval.vector.retrieve.assert_awaited_once_with(
        query="question",
        top_k=4,
        fetch_k=8,
        rerank=False,
        metadata_filters={"kb_id": "kb-1"},
    )
    sparse_arguments = retrieval.sparse.retrieve.await_args.kwargs
    assert sparse_arguments["query"] == "question"
    assert sparse_arguments["kb_ids"] == ["kb-1"]
    assert sparse_arguments["kb_options"]["kb-1"]["top_k_sparse"] == 3
    retrieval.fusion.fuse.assert_awaited_once_with(
        dense_results=[], sparse_results=[], top_k=7
    )
    retrieval.database.get_documents_with_metadata_batch.assert_awaited_once_with(
        {"doc-a", "doc-b"}
    )
    assert len(results) == 1
    result = results[0]
    assert (result.chunk_id, result.doc_name, result.kb_name, result.content) == (
        "chunk-a",
        "doc-a.md",
        "manual",
        "first answer",
    )
    assert result.metadata == {"chunk_index": 2, "char_count": 12}


@pytest.mark.asyncio
async def test_missing_document_metadata_is_not_returned(retrieval):
    del retrieval.database.get_documents_with_metadata_batch.return_value["doc-a"]
    results = await retrieval.manager.retrieve(
        "question", ["kb-1"], {"kb-1": retrieval.helper}
    )
    assert [item.chunk_id for item in results] == ["chunk-b"]


@pytest.mark.asyncio
async def test_reranker_failure_keeps_fused_results(retrieval):
    reranker = SimpleNamespace(
        rerank=AsyncMock(side_effect=RuntimeError("unavailable"))
    )
    retrieval.vector.rerank_provider = reranker
    results = await retrieval.manager.retrieve(
        "question", ["kb-1"], {"kb-1": retrieval.helper}
    )
    assert [item.chunk_id for item in results] == ["chunk-a", "chunk-b"]
    reranker.rerank.assert_awaited_once_with(
        query="question", documents=["first answer", "second answer"]
    )


@pytest.mark.asyncio
async def test_reranker_scores_determine_final_order(retrieval):
    retrieval.vector.rerank_provider = SimpleNamespace(
        rerank=AsyncMock(
            return_value=[
                SimpleNamespace(index=0, relevance_score=0.1),
                SimpleNamespace(index=1, relevance_score=0.8),
            ]
        )
    )
    results = await retrieval.manager.retrieve(
        "question", ["kb-1"], {"kb-1": retrieval.helper}, top_m_final=1
    )
    assert [(item.chunk_id, item.score) for item in results] == [("chunk-b", 0.8)]


@pytest.mark.asyncio
async def test_one_failed_dense_store_does_not_drop_healthy_results(retrieval):
    hit = SimpleNamespace(similarity=0.7)
    healthy = SimpleNamespace(retrieve=AsyncMock(return_value=[hit]))
    broken = SimpleNamespace(
        retrieve=AsyncMock(side_effect=RuntimeError("damaged index"))
    )
    results = await retrieval.manager._dense_retrieve(
        "question",
        ["broken", "healthy"],
        {
            "broken": {"vec_db": broken, "top_k_dense": 4},
            "healthy": {"vec_db": healthy, "top_k_dense": 4},
        },
    )
    assert results == [hit]
    healthy.retrieve.assert_awaited_once_with(
        query="question",
        top_k=4,
        fetch_k=8,
        rerank=False,
        metadata_filters={"kb_id": "healthy"},
    )
