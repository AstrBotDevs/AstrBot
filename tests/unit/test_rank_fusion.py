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
    dense_results = [
        _dense_result("small-exact", 0.99),
        _dense_result("large-1", 0.95),
        _dense_result("large-2", 0.90),
    ]
    sparse_results = [
        _sparse_result("large-1", "kb-large", 12.0, 1),
        _sparse_result("large-2", "kb-large", 10.0, 2),
        _sparse_result("small-exact", "kb-small", 0.01, 1),
    ]

    results = await RankFusion(kb_db=None).fuse(dense_results, sparse_results)

    assert [result.chunk_id for result in results] == [
        "small-exact",
        "large-1",
        "large-2",
    ]
    assert results[0].score == pytest.approx(2 / 61)


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
