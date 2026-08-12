import json
from types import SimpleNamespace

import pytest

from astrbot.core.db.vec_db.base import Result
from astrbot.core.knowledge_base.retrieval.rank_fusion import RankFusion
from astrbot.core.knowledge_base.retrieval.sparse_retriever import SparseResult


def _dense_result(chunk_id: str, similarity: float) -> Result:
    return Result(
        similarity=similarity,
        data={"doc_id": chunk_id, "text": chunk_id, "metadata": "{}"},
    )


def _dense_result_with_metadata(
    chunk_id: str,
    similarity: float,
    kb_id: str,
    doc_id: str,
    content: str,
) -> Result:
    return Result(
        similarity=similarity,
        data={
            "doc_id": chunk_id,
            "text": content,
            "metadata": json.dumps(
                {"chunk_index": 0, "kb_doc_id": doc_id, "kb_id": kb_id}
            ),
        },
    )


def _sparse_result(
    chunk_id: str,
    kb_id: str,
    score: float,
    rank: int,
) -> SparseResult:
    return SparseResult(
        chunk_index=0,
        chunk_id=chunk_id,
        doc_id=f"doc-{chunk_id}",
        kb_id=kb_id,
        content=chunk_id,
        score=score,
        rank=rank,
    )


@pytest.mark.asyncio
async def test_rank_fusion_prefers_sparse_payload_when_identifier_overlaps():
    fusion = RankFusion(kb_db=SimpleNamespace(), k=60)
    dense_results = [
        Result(
            similarity=0.9,
            data={
                "doc_id": "chunk-1",
                "metadata": json.dumps(
                    {
                        "chunk_index": 9,
                        "kb_doc_id": "doc-dense",
                        "kb_id": "kb-dense",
                    }
                ),
                "text": "dense text",
            },
        )
    ]
    sparse_results = [
        SparseResult(
            chunk_id="chunk-1",
            chunk_index=1,
            doc_id="doc-sparse",
            kb_id="kb-sparse",
            content="sparse text",
            score=0.8,
        )
    ]

    fused_results = await fusion.fuse(dense_results, sparse_results, top_k=1)

    assert len(fused_results) == 1
    assert fused_results[0].doc_id == "doc-sparse"
    assert fused_results[0].kb_id == "kb-sparse"
    assert fused_results[0].content == "sparse text"


@pytest.mark.asyncio
async def test_rank_fusion_uses_dense_metadata_when_sparse_result_missing():
    fusion = RankFusion(kb_db=SimpleNamespace(), k=60)
    dense_results = [
        Result(
            similarity=0.9,
            data={
                "doc_id": "chunk-2",
                "metadata": json.dumps(
                    {
                        "chunk_index": 3,
                        "kb_doc_id": "doc-2",
                        "kb_id": "kb-2",
                    }
                ),
                "text": "dense fallback text",
            },
        )
    ]

    fused_results = await fusion.fuse(dense_results, [], top_k=1)

    assert len(fused_results) == 1
    assert fused_results[0].chunk_id == "chunk-2"
    assert fused_results[0].chunk_index == 3
    assert fused_results[0].doc_id == "doc-2"
    assert fused_results[0].kb_id == "kb-2"
    assert fused_results[0].content == "dense fallback text"


@pytest.mark.asyncio
async def test_rank_fusion_uses_source_rank_for_independent_sparse_indexes():
    """RRF must use rank inside each independent sparse index, not score order."""
    sparse_results = [
        _sparse_result("large-1", "kb-large", 12.0, 2),
        _sparse_result("small-exact", "kb-small", 0.01, 1),
    ]

    results = await RankFusion(kb_db=None, dense_weight=0).fuse([], sparse_results)

    assert [result.chunk_id for result in results] == ["small-exact", "large-1"]
    assert results[0].score == pytest.approx(results[1].score)


@pytest.mark.asyncio
async def test_rank_fusion_uses_stable_tiebreakers():
    """Equivalent RRF scores are deterministic across process runs."""
    sparse_results = [
        _sparse_result("chunk-b", "kb", 10.0, 1),
        _sparse_result("chunk-a", "kb", 10.0, 1),
    ]

    forward = await RankFusion(kb_db=None).fuse([], sparse_results)
    reverse = await RankFusion(kb_db=None).fuse([], list(reversed(sparse_results)))

    assert [result.chunk_id for result in forward] == ["chunk-a", "chunk-b"]
    assert [result.chunk_id for result in reverse] == ["chunk-a", "chunk-b"]


@pytest.mark.asyncio
@pytest.mark.parametrize("top_k", [0, -1])
async def test_rank_fusion_returns_no_results_for_non_positive_top_k(top_k: int):
    """An empty request must not parse malformed retrieval payloads."""
    malformed_dense_result = Result(
        similarity=0.9,
        data={"doc_id": "chunk-1"},
    )

    results = await RankFusion(kb_db=None).fuse(
        [malformed_dense_result],
        [],
        top_k=top_k,
    )

    assert results == []


@pytest.mark.asyncio
async def test_rank_fusion_keeps_distinct_chunks_from_same_document():
    dense_results = [
        _dense_result_with_metadata("chunk-a1", 0.99, "kb", "doc-a", "first"),
        _dense_result_with_metadata("chunk-a2", 0.98, "kb", "doc-a", "second"),
    ]
    sparse_results = [
        SparseResult(0, "chunk-a1", "doc-a", "kb", "first", 10.0, 1),
        SparseResult(1, "chunk-a2", "doc-a", "kb", "second", 9.0, 2),
    ]

    results = await RankFusion(kb_db=None).fuse(dense_results, sparse_results)

    assert [result.chunk_id for result in results] == ["chunk-a1", "chunk-a2"]


@pytest.mark.asyncio
async def test_rank_fusion_calibrates_dense_scores_across_knowledge_bases():
    dense_results = [
        _dense_result_with_metadata("strong", 0.99, "large", "doc-1", "strong"),
        _dense_result_with_metadata("moderate", 0.80, "large", "doc-2", "moderate"),
        _dense_result_with_metadata("weak", 0.10, "small", "doc-3", "weak"),
    ]
    sparse_results = [
        SparseResult(0, "strong", "large", "large", "strong", 10.0, 1),
        SparseResult(1, "moderate", "large", "large", "moderate", 5.0, 2),
        SparseResult(0, "weak", "small", "small", "weak", 0.01, 1),
    ]

    results = await RankFusion(kb_db=None).fuse(dense_results, sparse_results)

    assert [result.chunk_id for result in results] == ["strong", "moderate", "weak"]
