from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request

from astrbot.core.provider.provider import EmbeddingProvider
from astrbot.dashboard.api.knowledge_bases import (
    list_knowledge_bases,
)
from astrbot.dashboard.schemas import (
    KnowledgeBaseRequest,
)
from astrbot.dashboard.services.knowledge_base_service import (
    KnowledgeBaseService,
    KnowledgeBaseServiceError,
)


class FakeEmbeddingProvider(EmbeddingProvider):
    def __init__(self):
        super().__init__({}, {})

    async def get_embedding(self, text: str) -> list[float]:
        return [0.1, 0.2]

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        return [[0.1, 0.2] for _ in text]

    def get_dim(self) -> int:
        return 2


def make_service(kb_manager) -> KnowledgeBaseService:
    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    service.core_lifecycle = SimpleNamespace(kb_manager=kb_manager)
    service.upload_progress = {}
    service.upload_tasks = {}
    return service


def make_kb(kb_id: str, kb_name: str):
    return SimpleNamespace(
        kb_id=kb_id,
        kb_name=kb_name,
        description="description",
        emoji="book",
        embedding_provider_id="embedding-1",
        rerank_provider_id="rerank-1",
        chunk_size=512,
        chunk_overlap=50,
        top_k_dense=50,
        top_k_sparse=50,
        top_m_final=5,
        model_dump=lambda: {"kb_id": kb_id, "kb_name": kb_name},
    )


def make_request(query_string: bytes) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/knowledge-bases",
            "query_string": query_string,
            "headers": [],
        }
    )


@pytest.mark.asyncio
async def test_list_kbs_applies_pagination():
    kb_manager = MagicMock()
    kb_manager.list_kbs = AsyncMock(
        return_value=[
            make_kb("kb-1", "one"),
            make_kb("kb-2", "two"),
            make_kb("kb-3", "three"),
        ]
    )
    kb_manager.get_kb = AsyncMock(
        side_effect=lambda kb_id: SimpleNamespace(init_error=None)
    )
    service = make_service(kb_manager)

    result = await service.list_kbs(page=2, page_size=2)

    assert result == {
        "items": [{"kb_id": "kb-3", "kb_name": "three"}],
        "page": 2,
        "page_size": 2,
        "total": 3,
    }


@pytest.mark.asyncio
async def test_list_kbs_without_page_size_returns_all_items():
    kb_manager = MagicMock()
    kb_manager.list_kbs = AsyncMock(
        return_value=[
            make_kb("kb-1", "one"),
            make_kb("kb-2", "two"),
            make_kb("kb-3", "three"),
        ]
    )
    kb_manager.get_kb = AsyncMock(
        side_effect=lambda kb_id: SimpleNamespace(init_error=None)
    )
    service = make_service(kb_manager)

    result = await service.list_kbs(page=1, page_size=None)

    assert result == {
        "items": [
            {"kb_id": "kb-1", "kb_name": "one"},
            {"kb_id": "kb-2", "kb_name": "two"},
            {"kb_id": "kb-3", "kb_name": "three"},
        ],
        "page": 1,
        "page_size": 3,
        "total": 3,
    }


@pytest.mark.asyncio
async def test_list_route_preserves_unpaginated_default():
    service = MagicMock()
    service.list_kbs = AsyncMock(return_value={"items": [], "total": 0})

    response = await list_knowledge_bases(
        make_request(b""),
        _auth=object(),
        service=service,
    )

    assert response["status"] == "ok"
    service.list_kbs.assert_awaited_once_with(page=1, page_size=None)


@pytest.mark.asyncio
async def test_list_route_uses_default_page_size_when_page_is_explicit():
    service = MagicMock()
    service.list_kbs = AsyncMock(return_value={"items": [], "total": 0})

    response = await list_knowledge_bases(
        make_request(b"page=2"),
        _auth=object(),
        service=service,
    )

    assert response["status"] == "ok"
    service.list_kbs.assert_awaited_once_with(page=2, page_size=20)


@pytest.mark.asyncio
async def test_create_kb_accepts_legacy_name_field():
    kb = make_kb("kb-1", "From Name")
    kb_manager = MagicMock()
    kb_manager.provider_manager.get_provider_by_id = AsyncMock(
        return_value=FakeEmbeddingProvider()
    )
    kb_manager.create_kb = AsyncMock(return_value=SimpleNamespace(kb=kb))
    service = make_service(kb_manager)

    result, message = await service.create_kb(
        {
            "name": "From Name",
            "embedding_provider_id": "embedding-1",
            "top_k_dense": 12,
            "top_k_sparse": 8,
            "top_m_final": 3,
        }
    )

    assert message == "创建知识库成功"
    assert result == {"kb_id": "kb-1", "kb_name": "From Name"}
    kb_manager.create_kb.assert_awaited_once_with(
        kb_name="From Name",
        description=None,
        emoji=None,
        embedding_provider_id="embedding-1",
        rerank_provider_id=None,
        chunk_size=None,
        chunk_overlap=None,
        top_k_dense=12,
        top_k_sparse=8,
        top_m_final=3,
    )


@pytest.mark.asyncio
async def test_update_kb_preserves_omitted_fields():
    kb = make_kb("kb-1", "Docs")
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=SimpleNamespace(kb=kb))
    kb_manager.update_kb = AsyncMock(return_value=SimpleNamespace(kb=kb))
    service = make_service(kb_manager)

    await service.update_kb({"kb_id": "kb-1", "chunk_size": 1024})

    kb_manager.update_kb.assert_awaited_once_with(
        kb_id="kb-1",
        kb_name="Docs",
        description="description",
        emoji="book",
        embedding_provider_id="embedding-1",
        rerank_provider_id="rerank-1",
        chunk_size=1024,
        chunk_overlap=50,
        top_k_dense=50,
        top_k_sparse=50,
        top_m_final=5,
    )


@pytest.mark.asyncio
async def test_update_kb_allows_explicit_rerank_provider_clear():
    kb = make_kb("kb-1", "Docs")
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=SimpleNamespace(kb=kb))
    kb_manager.update_kb = AsyncMock(return_value=SimpleNamespace(kb=kb))
    service = make_service(kb_manager)

    await service.update_kb({"kb_id": "kb-1", "rerank_provider_id": None})

    kb_manager.update_kb.assert_awaited_once()
    assert kb_manager.update_kb.await_args.kwargs["rerank_provider_id"] is None


def test_knowledge_base_schemas_match_service_contract():
    create_payload = KnowledgeBaseRequest(
        kb_name="Docs",
        name="Legacy",
        emoji="book",
        top_k_dense=12,
        top_k_sparse=8,
        top_m_final=3,
        kb_id="body-kb-id",
    ).canonical_payload()
    assert create_payload == {
        "kb_name": "Docs",
        "emoji": "book",
        "top_k_dense": 12,
        "top_k_sparse": 8,
        "top_m_final": 3,
    }
    assert "kb_id" not in create_payload


def test_knowledge_base_request_preserves_explicit_null_updates():
    payload = KnowledgeBaseRequest(rerank_provider_id=None).canonical_payload()

    assert payload == {"rerank_provider_id": None}


def test_knowledge_base_request_omits_unset_none_fields():
    payload = KnowledgeBaseRequest(kb_name="Docs").canonical_payload()

    assert payload == {"kb_name": "Docs"}


def test_knowledge_base_request_uses_legacy_name_as_input_alias():
    payload = KnowledgeBaseRequest(name="Legacy Name").canonical_payload()

    assert payload == {"kb_name": "Legacy Name"}


@pytest.mark.asyncio
async def test_create_kb_raises_when_kb_name_is_missing():
    kb_manager = MagicMock()
    service = make_service(kb_manager)

    with pytest.raises(KnowledgeBaseServiceError, match="知识库名称不能为空"):
        await service.create_kb({"embedding_provider_id": "embedding-1"})


@pytest.mark.asyncio
async def test_create_kb_raises_when_embedding_provider_is_missing():
    kb_manager = MagicMock()
    service = make_service(kb_manager)

    with pytest.raises(KnowledgeBaseServiceError, match="缺少参数 embedding_provider_id"):
        await service.create_kb({"kb_name": "Test KB"})

