import json

import pytest

from astrbot.core.db.vec_db.base import Result
from astrbot.core.knowledge_base.retrieval.rank_fusion import RankFusion
from astrbot.core.knowledge_base.retrieval.sparse_retriever import SparseResult


def make_dense_result(
    chunk_id: str,
    similarity: float,
    kb_id: str = "kb",
    doc_id: str | None = None,
    content: str | None = None,
) -> Result:
    return Result(
        similarity=similarity,
        data={
            "doc_id": chunk_id,
            "text": content if content is not None else chunk_id,
            "metadata": json.dumps(
                {
                    "chunk_index": 0,
                    "kb_doc_id": doc_id or f"doc-{chunk_id}",
                    "kb_id": kb_id,
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
    content: str | None = None,
) -> SparseResult:
    return SparseResult(
        chunk_index=0,
        chunk_id=chunk_id,
        doc_id=doc_id or f"doc-{chunk_id}",
        kb_id=kb_id,
        content=content if content is not None else chunk_id,
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
async def test_rank_fusion_keeps_distinct_chunks_from_the_same_document():
    dense_results = [
        make_dense_result("doc-a-best", 0.99, doc_id="doc-a"),
        make_dense_result("doc-a-second", 0.98, doc_id="doc-a"),
        make_dense_result("doc-a-third", 0.97, doc_id="doc-a"),
        make_dense_result("doc-b", 0.97),
    ]
    sparse_results = [
        make_sparse_result("doc-a-best", "kb", 10.0, 1, doc_id="doc-a"),
        make_sparse_result("doc-a-second", "kb", 9.0, 2, doc_id="doc-a"),
        make_sparse_result("doc-a-third", "kb", 8.0, 3, doc_id="doc-a"),
        make_sparse_result("doc-b", "kb", 7.0, 4, doc_id="doc-b"),
    ]

    results = await RankFusion(kb_db=None).fuse(
        dense_results=dense_results,
        sparse_results=sparse_results,
        top_k=4,
    )

    assert [result.chunk_id for result in results] == [
        "doc-a-best",
        "doc-a-second",
        "doc-a-third",
        "doc-b",
    ]
    assert [result.doc_id for result in results] == [
        "doc-a",
        "doc-a",
        "doc-a",
        "doc-b",
    ]


@pytest.mark.asyncio
async def test_rank_fusion_deduplicates_only_exact_chunk_text():
    dense_results = [
        make_dense_result("duplicate-best", 0.99, content="same text"),
        make_dense_result("duplicate-second", 0.98, content="same text"),
        make_dense_result("near-duplicate", 0.97, content="same text "),
        make_dense_result("unique", 0.96),
    ]
    sparse_results = [
        make_sparse_result("duplicate-best", "kb", 10.0, 1, content="same text"),
        make_sparse_result(
            "duplicate-second",
            "kb",
            9.0,
            2,
            content="same text",
        ),
        make_sparse_result("near-duplicate", "kb", 8.0, 3, content="same text "),
        make_sparse_result("unique", "kb", 7.0, 4),
    ]

    results = await RankFusion(kb_db=None).fuse(
        dense_results=dense_results,
        sparse_results=sparse_results,
        top_k=4,
    )

    assert [result.chunk_id for result in results] == [
        "duplicate-best",
        "near-duplicate",
        "unique",
    ]


@pytest.mark.asyncio
async def test_rank_fusion_does_not_promote_a_single_low_scoring_kb_result():
    dense_results = [
        make_dense_result("strong", 0.99, kb_id="kb-large"),
        make_dense_result("moderate", 0.80, kb_id="kb-large"),
        make_dense_result("weak", 0.10, kb_id="kb-small"),
    ]
    sparse_results = [
        make_sparse_result("strong", "kb-large", 10.0, 1),
        make_sparse_result("moderate", "kb-large", 5.0, 2),
        make_sparse_result("weak", "kb-small", 0.01, 1),
    ]

    results = await RankFusion(kb_db=None).fuse(
        dense_results=dense_results,
        sparse_results=sparse_results,
    )

    assert [result.chunk_id for result in results] == [
        "strong",
        "moderate",
        "weak",
    ]
    assert results[-1].score == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_rank_fusion_rescues_sparse_only_exact_match_from_dense_field():
    """仅被稀疏通道召回的精确词面匹配必须能进入融合后的最终结果。

    复现 #9868：embedding 对大小写变体召回失败，而 BM25 把包含该词面
    的知识块排到了第 1 位。旧实现在缺失通道上按 0 分计入加权，导致仅
    被稀疏通道召回的候选在 dense_weight=0.9 时最高只能拿到 0.1 分，排
    不过稠密通道的中游候选，从而完全掉出最终 top-k。
    """
    dense_results = [
        make_dense_result(f"dense-{rank}", 0.90 - rank / 100) for rank in range(1, 51)
    ]
    sparse_results = [
        make_sparse_result("oni-exact", "kb", 30.0, 1),
        *[
            make_sparse_result(f"sparse-{rank}", "kb", 20 - rank, rank + 1)
            for rank in range(1, 6)
        ],
    ]

    results = await RankFusion(kb_db=None, dense_weight=0.9).fuse(
        dense_results=dense_results,
        sparse_results=sparse_results,
        top_k=5,
    )

    assert "oni-exact" in [result.chunk_id for result in results]


@pytest.mark.asyncio
async def test_rank_fusion_rescues_dense_only_top_hit_from_sparse_field():
    """与稀疏侧对称：仅被稠密通道召回的高分候选也不能被压掉。

    在 sparse_weight 偏高的配置（dense_weight=0.1）下，稠密侧唯一召回
    的最强候选同样不应因稀疏通道缺失而被按 0 分惩罚。
    """
    sparse_results = [
        make_sparse_result(f"sparse-{rank}", "kb", 30 - rank, rank)
        for rank in range(1, 51)
    ]
    dense_results = [
        make_dense_result("dense-exact", 0.99),
        *[
            make_dense_result(f"dense-{rank}", 0.60 - rank / 100)
            for rank in range(1, 6)
        ],
    ]

    results = await RankFusion(kb_db=None, dense_weight=0.1).fuse(
        dense_results=dense_results,
        sparse_results=sparse_results,
        top_k=5,
    )

    assert "dense-exact" in [result.chunk_id for result in results]
