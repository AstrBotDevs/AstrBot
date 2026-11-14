"""Regression tests for unavailable TEI clients during knowledge retrieval."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import aiohttp
import pytest
import pytest_asyncio

import astrbot.api  # noqa: F401  # Import first to avoid a circular import.
from astrbot.core.provider.sources.tei_rerank_source import TEIRerankProvider


@pytest_asyncio.fixture(params=["missing", "closed"])
async def unavailable_provider(request):
    provider = TEIRerankProvider.__new__(TEIRerankProvider)
    provider.client = None
    if request.param == "closed":
        provider.client = aiohttp.ClientSession()
        await provider.client.close()
    return provider


@pytest_asyncio.fixture
async def healthy_provider():
    provider = TEIRerankProvider.__new__(TEIRerankProvider)
    provider.base_url = "https://rerank.example.test"
    provider.truncate = False
    provider.raw_scores = False
    provider.return_text = False
    async with aiohttp.ClientSession() as client:
        provider.client = client
        yield provider


@pytest.mark.asyncio
async def test_tei_rerank_maps_response_order_and_top_n(healthy_provider, monkeypatch):
    response = Mock(status=200)
    response.json = AsyncMock(
        return_value=[
            {"index": 2, "score": 0.9},
            {"index": 0, "score": 0.7},
            {"index": 1, "score": 0.5},
        ]
    )
    request = AsyncMock()
    request.__aenter__.return_value = response
    post = Mock(return_value=request)
    monkeypatch.setattr(aiohttp.ClientSession, "post", post)

    results = await healthy_provider.rerank(
        "query", ["first", "second", "third"], top_n=2
    )

    assert [(result.index, result.relevance_score) for result in results] == [
        (2, 0.9),
        (0, 0.7),
    ]
    post.assert_called_once_with(
        "https://rerank.example.test/rerank",
        json={"query": "query", "texts": ["first", "second", "third"]},
    )


@pytest.mark.asyncio
async def test_tei_rerank_skips_http_for_empty_documents(healthy_provider, monkeypatch):
    post = Mock()
    monkeypatch.setattr(aiohttp.ClientSession, "post", post)

    results = await healthy_provider.rerank("query", [])

    assert results == []
    post.assert_not_called()


@pytest.mark.asyncio
async def test_tei_rerank_raises_for_unavailable_client(unavailable_provider):
    with pytest.raises(RuntimeError, match="not initialized or closed"):
        await unavailable_provider.rerank("query", ["first", "second"])


@pytest.mark.asyncio
async def test_retrieval_preserves_fused_candidates_for_unavailable_tei(
    unavailable_provider, monkeypatch
):
    from astrbot.core.knowledge_base.retrieval.manager import RetrievalManager
    from astrbot.core.knowledge_base.retrieval.rank_fusion import FusedResult

    rerank = AsyncMock(wraps=unavailable_provider.rerank)
    monkeypatch.setattr(unavailable_provider, "rerank", rerank)

    candidates = [
        FusedResult(
            chunk_id="chunk-first",
            chunk_index=0,
            doc_id="document",
            kb_id="kb",
            content="first",
            score=0.8,
        ),
        FusedResult(
            chunk_id="chunk-second",
            chunk_index=1,
            doc_id="document",
            kb_id="kb",
            content="second",
            score=0.7,
        ),
    ]
    kb_db = SimpleNamespace(
        get_documents_with_metadata_batch=AsyncMock(
            return_value={
                "document": {
                    "document": SimpleNamespace(doc_name="document.txt"),
                    "knowledge_base": SimpleNamespace(kb_name="Knowledge"),
                }
            }
        )
    )
    manager = RetrievalManager(
        sparse_retriever=SimpleNamespace(retrieve=AsyncMock(return_value=[])),
        rank_fusion=SimpleNamespace(fuse=AsyncMock(return_value=candidates)),
        kb_db=kb_db,
    )
    helper = SimpleNamespace(
        get_rp=AsyncMock(return_value=unavailable_provider),
        kb=SimpleNamespace(
            top_k_dense=50,
            top_k_sparse=50,
            top_m_final=5,
            rerank_provider_id="tei",
        ),
        vec_db=SimpleNamespace(
            retrieve=AsyncMock(return_value=[]),
            rerank_provider=unavailable_provider,
        ),
    )

    results = await manager.retrieve(
        query="query",
        kb_ids=["kb"],
        kb_id_helper_map={"kb": helper},
        top_m_final=2,
    )

    rerank.assert_awaited_once_with(query="query", documents=["first", "second"])
    assert [(result.chunk_id, result.content, result.score) for result in results] == [
        ("chunk-first", "first", 0.8),
        ("chunk-second", "second", 0.7),
    ]
