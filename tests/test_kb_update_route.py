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


@pytest.mark.asyncio
async def test_update_kb_omits_unprovided_rerank_provider_id():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
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
