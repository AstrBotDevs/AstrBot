from unittest.mock import AsyncMock, MagicMock

import pytest

# Importing the core lifecycle first resolves the import cycle between
# astrbot.core.provider.manager and astrbot.core.knowledge_base.
import astrbot.core.core_lifecycle  # noqa: F401
from astrbot.core.knowledge_base.retrieval.manager import (
    RetrievalManager,
    RetrievalResult,
)
from astrbot.core.provider.entities import RerankResult
from astrbot.core.provider.sources.xinference_rerank_source import (
    XinferenceRerankProvider,
)


def _provider(model=None) -> XinferenceRerankProvider:
    provider = XinferenceRerankProvider.__new__(XinferenceRerankProvider)
    provider.model = model
    return provider


@pytest.mark.asyncio
async def test_rerank_raises_when_model_is_not_initialized():
    with pytest.raises(RuntimeError, match="not initialized"):
        await _provider(model=None).rerank("query", ["doc"])


@pytest.mark.asyncio
async def test_rerank_propagates_upstream_failures():
    model = MagicMock()
    model.rerank = AsyncMock(side_effect=ConnectionError("xinference unavailable"))

    with pytest.raises(ConnectionError, match="xinference unavailable"):
        await _provider(model=model).rerank("query", ["doc a", "doc b"])


@pytest.mark.asyncio
async def test_rerank_maps_results():
    model = MagicMock()
    model.rerank = AsyncMock(
        return_value={"results": [{"index": 1, "relevance_score": 0.9}]}
    )

    results = await _provider(model=model).rerank("query", ["doc a", "doc b"], 1)

    model.rerank.assert_awaited_once_with(["doc a", "doc b"], "query", 1)
    assert results == [RerankResult(index=1, relevance_score=0.9)]


def _result(i: int) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=f"chunk-{i}",
        doc_id="doc",
        doc_name="doc.md",
        kb_id="kb",
        kb_name="kb",
        content=f"content {i}",
        score=1.0 - i / 10,
        metadata={},
    )


@pytest.mark.asyncio
async def test_manager_keeps_fused_results_when_rerank_returns_nothing():
    manager = RetrievalManager.__new__(RetrievalManager)
    provider = MagicMock()
    provider.rerank = AsyncMock(return_value=[])
    fused = [_result(0), _result(1), _result(2)]

    reranked = await manager._rerank(
        query="query", results=fused, top_k=2, rerank_provider=provider
    )

    assert reranked == fused[:2]


@pytest.mark.asyncio
async def test_manager_applies_rerank_scores():
    manager = RetrievalManager.__new__(RetrievalManager)
    provider = MagicMock()
    provider.rerank = AsyncMock(
        return_value=[
            RerankResult(index=1, relevance_score=0.95),
            RerankResult(index=0, relevance_score=0.10),
        ]
    )
    fused = [_result(0), _result(1)]

    reranked = await manager._rerank(
        query="query", results=fused, top_k=2, rerank_provider=provider
    )

    assert [r.chunk_id for r in reranked] == ["chunk-1", "chunk-0"]
    assert [r.score for r in reranked] == [0.95, 0.10]
