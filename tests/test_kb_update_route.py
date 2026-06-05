from unittest.mock import AsyncMock, MagicMock

import pytest
from quart import Quart


def _build_route_with_manager(kb_manager: MagicMock):
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    route = KnowledgeBaseRoute.__new__(KnowledgeBaseRoute)
    route._get_kb_manager = MagicMock(return_value=kb_manager)
    return route


def _build_kb_helper(rerank_provider_id: str | None = "rerank-1"):
    from astrbot.core.knowledge_base.models import KnowledgeBase

    kb = KnowledgeBase(
        kb_id="kb-1",
        kb_name="kb",
        embedding_provider_id="emb-1",
        rerank_provider_id=rerank_provider_id,
    )
    helper = MagicMock()
    helper.kb = kb
    return helper


def _build_kb_helper_with_options(**kwargs):
    from astrbot.core.knowledge_base.models import KnowledgeBase

    kb = KnowledgeBase(
        kb_id=kwargs.get("kb_id", "kb-1"),
        kb_name=kwargs.get("kb_name", "kb"),
        embedding_provider_id="emb-1",
        rerank_provider_id=kwargs.get("rerank_provider_id", "rerank-1"),
        chunk_size=kwargs.get("chunk_size", 512),
        chunk_overlap=kwargs.get("chunk_overlap", 50),
        top_k_dense=kwargs.get("top_k_dense", 50),
        top_k_sparse=kwargs.get("top_k_sparse", 50),
        top_m_final=kwargs.get("top_m_final", 5),
        index_type=kwargs.get("index_type", "flat"),
    )
    helper = MagicMock()
    helper.kb = kb
    return helper


@pytest.mark.asyncio
async def test_update_kb_omits_unprovided_rerank_provider_id():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=_build_kb_helper_with_options())
    kb_manager.update_kb = AsyncMock(return_value=_build_kb_helper())
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/update",
        method="POST",
        json={"kb_id": "kb-1", "chunk_size": 1024},
    ):
        response = await KnowledgeBaseRoute.update_kb(route)

    assert response["status"] == "ok"
    kwargs = kb_manager.update_kb.await_args.kwargs
    assert kwargs["kb_id"] == "kb-1"
    assert kwargs["chunk_size"] == 1024
    assert "rerank_provider_id" not in kwargs


@pytest.mark.asyncio
async def test_update_kb_explicit_null_forwards_rerank_provider_id():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=_build_kb_helper_with_options())
    kb_manager.update_kb = AsyncMock(return_value=_build_kb_helper(None))
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/update",
        method="POST",
        json={"kb_id": "kb-1", "rerank_provider_id": None},
    ):
        response = await KnowledgeBaseRoute.update_kb(route)

    assert response["status"] == "ok"
    kwargs = kb_manager.update_kb.await_args.kwargs
    assert kwargs["kb_id"] == "kb-1"
    assert kwargs["rerank_provider_id"] is None


@pytest.mark.asyncio
async def test_update_kb_rejects_overlap_not_less_than_chunk_size():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=_build_kb_helper_with_options())
    kb_manager.update_kb = AsyncMock()
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/update",
        method="POST",
        json={"kb_id": "kb-1", "chunk_size": 100, "chunk_overlap": 100},
    ):
        response = await KnowledgeBaseRoute.update_kb(route)

    assert response["status"] == "error"
    assert "chunk_overlap" in response["message"]
    kb_manager.update_kb.assert_not_awaited()


@pytest.mark.asyncio
async def test_retrieve_accepts_kb_ids():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.retrieve = AsyncMock(return_value={"results": []})
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/retrieve",
        method="POST",
        json={"query": "hello", "kb_ids": ["kb-1"], "top_k": 3},
    ):
        response = await KnowledgeBaseRoute.retrieve(route)

    assert response["status"] == "ok"
    kb_manager.retrieve.assert_awaited_once_with(
        query="hello",
        kb_names=None,
        kb_ids=["kb-1"],
        top_m_final=3,
    )


@pytest.mark.asyncio
async def test_retrieve_rejects_invalid_top_k():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.retrieve = AsyncMock()
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/retrieve",
        method="POST",
        json={"query": "hello", "kb_ids": ["kb-1"], "top_k": 0},
    ):
        response = await KnowledgeBaseRoute.retrieve(route)

    assert response["status"] == "error"
    assert "top_k" in response["message"]
    kb_manager.retrieve.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_documents_returns_total_and_uses_requested_pagination():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = MagicMock()
    doc = MagicMock()
    doc.model_dump.return_value = {"doc_id": "doc-1", "doc_name": "alpha.md"}
    kb_helper.list_documents = AsyncMock(return_value=[doc])
    kb_helper.count_documents = AsyncMock(return_value=123)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/document/list?kb_id=kb-1&page=3&page_size=25&search=alpha",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.list_documents(route)

    assert response["status"] == "ok"
    assert response["data"]["items"] == [{"doc_id": "doc-1", "doc_name": "alpha.md"}]
    assert response["data"]["page"] == 3
    assert response["data"]["page_size"] == 25
    assert response["data"]["total"] == 123
    kb_helper.list_documents.assert_awaited_once_with(
        offset=50,
        limit=25,
        search="alpha",
    )
    kb_helper.count_documents.assert_awaited_once_with(search="alpha")
