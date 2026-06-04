"""Tests for sparse retrieval score consistency between FTS5 and BM25 paths.

RRF only uses rank positions, not score magnitudes. The sparse retrieval stage
just needs consistent sort direction: lower-is-better, ascending order.
"""

import json
from unittest.mock import AsyncMock

import pytest

from astrbot.core.knowledge_base.retrieval.sparse_retriever import (
    SparseResult,
    SparseRetriever,
)


def _make_fake_doc(doc_id: str, text: str, metadata: dict) -> dict:
    return {
        "id": hash(doc_id) % 10000,
        "doc_id": doc_id,
        "text": text,
        "metadata": json.dumps(metadata),
        "created_at": "2025-01-01T00:00:00",
        "updated_at": "2025-01-01T00:00:00",
    }


class TestSparseRetrieverScoreDirection:
    """Verify FTS5 and BM25 both use lower-is-better, ascending sort."""

    @pytest.mark.asyncio
    async def test_fts5_best_match_has_lowest_score(self):
        """FTS5: raw bm25=0 (perfect) → score=0, sorts first (ascending)."""
        sr = SparseRetriever(kb_db=AsyncMock())
        sr._index_cache = {}

        vec_db = AsyncMock()
        vec_db.document_storage.search_sparse = AsyncMock(
            return_value=[
                {
                    "id": 1, "doc_id": "best", "text": "exact match",
                    "metadata": json.dumps({"chunk_index": 0, "kb_doc_id": "d1", "kb_id": "kb-a"}),
                    "score": 0.0,  # perfect
                    "created_at": "", "updated_at": "",
                },
                {
                    "id": 2, "doc_id": "worst", "text": "poor match",
                    "metadata": json.dumps({"chunk_index": 1, "kb_doc_id": "d1", "kb_id": "kb-a"}),
                    "score": 50.0,  # terrible
                    "created_at": "", "updated_at": "",
                },
            ],
        )

        kb_options = {"kb-a": {"vec_db": vec_db, "top_k_sparse": 10}}
        results = await sr.retrieve(query="test", kb_ids=["kb-a"], kb_options=kb_options)

        assert len(results) == 2
        assert results[0].chunk_id == "best", f"Best should be first, got {results[0].chunk_id}"
        assert results[0].score == 0.0  # lower-is-better
        assert results[0].score < results[1].score  # ascending

    @pytest.mark.asyncio
    async def test_fts5_negative_bm25_clamped_to_zero(self):
        """FTS5 bm25() negative values → clamped to 0 (same as perfect match)."""
        sr = SparseRetriever(kb_db=AsyncMock())
        sr._index_cache = {}

        vec_db = AsyncMock()
        vec_db.document_storage.search_sparse = AsyncMock(
            return_value=[
                {
                    "id": 1, "doc_id": "short-doc", "text": "short",
                    "metadata": json.dumps({"chunk_index": 0, "kb_doc_id": "d1", "kb_id": "kb-a"}),
                    "score": -8.56,  # FTS5 can be negative for short docs
                    "created_at": "", "updated_at": "",
                },
            ],
        )

        kb_options = {"kb-a": {"vec_db": vec_db, "top_k_sparse": 10}}
        results = await sr.retrieve(query="test", kb_ids=["kb-a"], kb_options=kb_options)

        assert len(results) == 1
        assert results[0].score == 0.0, (
            f"Negative raw bm25 should be clamped to 0, got {results[0].score}"
        )

    @pytest.mark.asyncio
    async def test_bm25_fallback_negates_scores(self):
        """BM25Okapi higher=better → negated to lower=better, ascending sort."""
        sr = SparseRetriever(kb_db=AsyncMock())
        sr._index_cache = {}

        vec_db = AsyncMock()
        vec_db.document_storage.get_documents = AsyncMock(
            return_value=[
                _make_fake_doc("chunk-best", "exact match hello world",
                               {"chunk_index": 0, "kb_doc_id": "d1", "kb_id": "kb-a"}),
                _make_fake_doc("chunk-worst", "unrelated content here",
                               {"chunk_index": 0, "kb_doc_id": "d2", "kb_id": "kb-a"}),
            ],
        )

        kb_options = {"kb-a": {"vec_db": vec_db, "top_k_sparse": 50}}
        results = await sr._retrieve_with_bm25(query="hello", kb_ids=["kb-a"], kb_options=kb_options)

        assert len(results) == 2
        # Best match should be most negative (negated highest BM25Okapi)
        assert results[0].score <= results[1].score, (
            f"Expected ascending sort (lower=better), got {[r.score for r in results]}"
        )
        # Best score should be <= 0 (negation of non-negative BM25Okapi)
        assert results[0].score <= 0, (
            f"BM25 fallback best match should be negative after negation, got {results[0].score}"
        )

    @pytest.mark.asyncio
    async def test_merged_fts5_and_bm25_sort_correctly(self):
        """Merge: FTS5 (0=best) + BM25 (neg=best) → ascending sort, both can be top."""
        fts = [
            SparseResult(chunk_id="fts-best", chunk_index=0, doc_id="d1",
                         kb_id="kb-a", content="a", score=0.0),
            SparseResult(chunk_id="fts-mid", chunk_index=1, doc_id="d1",
                         kb_id="kb-a", content="b", score=3.0),
            SparseResult(chunk_id="fts-worst", chunk_index=2, doc_id="d2",
                         kb_id="kb-a", content="c", score=12.5),
        ]
        bm25 = [
            SparseResult(chunk_id="bm25-good", chunk_index=0, doc_id="d3",
                         kb_id="kb-b", content="d", score=-15.0),  # negated best
            SparseResult(chunk_id="bm25-ok", chunk_index=1, doc_id="d3",
                         kb_id="kb-b", content="e", score=-5.0),
            SparseResult(chunk_id="bm25-poor", chunk_index=2, doc_id="d4",
                         kb_id="kb-b", content="f", score=0.0),  # negated worst
        ]

        merged = fts + bm25
        merged.sort(key=lambda x: x.score)  # ascending, lower=better

        # Expected: bm25-good(-15) < fts-best(0) < fts-mid(3) < bm25-ok(-5) < bm25-poor(0) < fts-worst(12.5)
        # Wait: -15 < -5 < 0 < 0 < 3 < 12.5
        assert merged[0].chunk_id == "bm25-good"
        assert merged[1].chunk_id == "bm25-ok"
        # fts-best(0) and bm25-poor(0) tie — stable sort preserves order
        assert merged[4].chunk_id == "fts-mid"
        assert merged[5].chunk_id == "fts-worst"

    @pytest.mark.asyncio
    async def test_fts5_and_bm25_both_contribute_to_sort(self):
        """Integration: both paths produce consistent lower-is-better scores."""
        sr = SparseRetriever(kb_db=AsyncMock())

        # KB "a" uses FTS5
        fts_vec_db = AsyncMock()
        fts_vec_db.document_storage.search_sparse = AsyncMock(
            return_value=[
                {
                    "id": 1, "doc_id": "fts-hit", "text": "test query match",
                    "metadata": json.dumps({"chunk_index": 0, "kb_doc_id": "d1", "kb_id": "kb-a"}),
                    "score": 0.0,
                },
            ],
        )

        # KB "b" falls back to BM25
        bm25_vec_db = AsyncMock()
        bm25_vec_db.document_storage.search_sparse = AsyncMock(return_value=None)
        bm25_vec_db.document_storage.get_documents = AsyncMock(
            return_value=[
                _make_fake_doc("bm25-hit", "test query result",
                               {"chunk_index": 0, "kb_doc_id": "d2", "kb_id": "kb-b"}),
                _make_fake_doc("bm25-miss", "unrelated",
                               {"chunk_index": 0, "kb_doc_id": "d3", "kb_id": "kb-b"}),
            ],
        )

        kb_options = {
            "kb-a": {"vec_db": fts_vec_db, "top_k_sparse": 10},
            "kb-b": {"vec_db": bm25_vec_db, "top_k_sparse": 10},
        }

        results = await sr.retrieve(query="test", kb_ids=["kb-a", "kb-b"], kb_options=kb_options)

        assert len(results) >= 2
        # Ascending order
        for i in range(len(results) - 1):
            assert results[i].score <= results[i + 1].score, (
                f"Not sorted ascending at index {i}: {results[i].score} > {results[i+1].score}"
            )
        # No out-of-range scores
        for r in results:
            assert r.score >= -1000.0, f"Unexpectedly low score: {r.score}"
