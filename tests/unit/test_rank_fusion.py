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
