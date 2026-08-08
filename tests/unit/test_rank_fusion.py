import json

import pytest

from astrbot.core.db.vec_db.base import Result
from astrbot.core.knowledge_base.retrieval.rank_fusion import RankFusion
from astrbot.core.knowledge_base.retrieval.sparse_retriever import SparseResult


def make_dense_result(chunk_id: str, similarity: float) -> Result:
    return Result(
        similarity=similarity,
        data={
            "doc_id": chunk_id,
            "text": chunk_id,
            "metadata": json.dumps(
                {
                    "chunk_index": 0,
                    "kb_doc_id": f"doc-{chunk_id}",
                    "kb_id": "kb",
                }
            ),
        },
    )


def make_sparse_result(
    chunk_id: str,
    kb_id: str,
    score: float,
    rank: int,
    doc_id: str | None = None,
) -> SparseResult:
    return SparseResult(
        chunk_index=0,
        chunk_id=chunk_id,
        doc_id=doc_id or f"doc-{chunk_id}",
        kb_id=kb_id,
        content=chunk_id,
        score=score,
        rank=rank,
    )


@pytest.mark.parametrize("dense_weight", [-0.1, 1.1])
def test_rank_fusion_rejects_invalid_dense_weight(dense_weight):
    with pytest.raises(ValueError, match="dense_weight"):
        RankFusion(kb_db=None, dense_weight=dense_weight)


@pytest.mark.asyncio
async def test_rank_fusion_returns_empty_for_non_positive_top_k():
    results = await RankFusion(kb_db=None).fuse(
        dense_results=[make_dense_result("chunk", 0.99)],
        sparse_results=[],
        top_k=0,
    )

    assert results == []


@pytest.mark.asyncio
async def test_rank_fusion_uses_source_rank_for_independent_sparse_indexes():
    dense_results = [
        make_dense_result("small-exact", 0.99),
        make_dense_result("large-1", 0.95),
        make_dense_result("large-2", 0.90),
    ]
    sparse_results = [
        make_sparse_result("large-1", "kb-large", 12.0, 1),
        make_sparse_result("large-2", "kb-large", 10.0, 2),
        make_sparse_result("small-exact", "kb-small", 0.00001, 1),
    ]

    results = await RankFusion(kb_db=None).fuse(
        dense_results=dense_results,
        sparse_results=sparse_results,
    )

    assert [result.chunk_id for result in results] == [
        "small-exact",
        "large-1",
        "large-2",
    ]
    assert results[0].score == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_rank_fusion_prefers_dense_signal_when_sources_disagree():
    dense_results = [
        make_dense_result("dense-first", 0.99),
        make_dense_result("sparse-first", 0.98),
    ]
    sparse_results = [
        make_sparse_result("sparse-first", "kb", 10.0, 1),
        make_sparse_result("dense-first", "kb", 9.0, 2),
    ]

    results = await RankFusion(kb_db=None).fuse(
        dense_results=dense_results,
        sparse_results=sparse_results,
    )

    assert [result.chunk_id for result in results] == [
        "dense-first",
        "sparse-first",
    ]
    assert results[0].score == pytest.approx(0.9)
    assert results[1].score == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_rank_fusion_uses_chunk_id_as_stable_final_tiebreaker():
    sparse_results = [
        make_sparse_result("chunk-b", "kb", 10.0, 1),
        make_sparse_result("chunk-a", "kb", 10.0, 1),
    ]

    forward_results = await RankFusion(kb_db=None).fuse(
        dense_results=[],
        sparse_results=sparse_results,
    )
    reverse_results = await RankFusion(kb_db=None).fuse(
        dense_results=[],
        sparse_results=list(reversed(sparse_results)),
    )

    assert [result.chunk_id for result in forward_results] == [
        "chunk-a",
        "chunk-b",
    ]
    assert [result.chunk_id for result in reverse_results] == [
        "chunk-a",
        "chunk-b",
    ]


@pytest.mark.asyncio
async def test_rank_fusion_does_not_overvalue_low_rank_source_overlap():
    dense_results = [make_dense_result("dense-best", 0.99)] + [
        make_dense_result(f"dense-{rank}", 0.9 - rank / 100) for rank in range(2, 51)
    ]
    sparse_results = [
        make_sparse_result(f"sparse-{rank}", "kb", 51 - rank, rank)
        for rank in range(1, 50)
    ] + [make_sparse_result("dense-50", "kb", 1.0, 50)]

    results = await RankFusion(kb_db=None).fuse(
        dense_results=dense_results,
        sparse_results=sparse_results,
        top_k=100,
    )
    result_ids = [result.chunk_id for result in results]

    assert result_ids[0] == "dense-best"
    assert result_ids.index("dense-best") < result_ids.index("dense-50")


@pytest.mark.asyncio
async def test_rank_fusion_keeps_only_the_best_chunk_per_document():
    dense_results = [
        make_dense_result("doc-a-best", 0.99),
        make_dense_result("doc-a-second", 0.98),
        make_dense_result("doc-b", 0.97),
    ]
    sparse_results = [
        make_sparse_result("doc-a-best", "kb", 10.0, 1, doc_id="doc-a"),
        make_sparse_result("doc-a-second", "kb", 9.0, 2, doc_id="doc-a"),
        make_sparse_result("doc-b", "kb", 8.0, 3, doc_id="doc-b"),
    ]

    results = await RankFusion(kb_db=None).fuse(
        dense_results=dense_results,
        sparse_results=sparse_results,
        top_k=2,
    )

    assert [result.chunk_id for result in results] == ["doc-a-best", "doc-b"]
    assert [result.doc_id for result in results] == ["doc-a", "doc-b"]
