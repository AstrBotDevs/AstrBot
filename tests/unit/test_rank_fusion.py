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
            "metadata": "{}",
        },
    )


def make_sparse_result(
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
    assert results[0].score == pytest.approx(2 / 61)


@pytest.mark.asyncio
async def test_rank_fusion_prefers_dense_rank_when_scores_are_equal():
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

    assert results[0].score == pytest.approx(results[1].score)
    assert [result.chunk_id for result in results] == [
        "dense-first",
        "sparse-first",
    ]


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
