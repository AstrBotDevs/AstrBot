from unittest.mock import AsyncMock, MagicMock, patch

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
async def test_get_capabilities_returns_backend_limits():
    from astrbot.core.knowledge_base.capabilities import (
        ALLOWED_UPLOAD_EXTENSIONS,
        CHUNK_PAGE_SIZE_OPTIONS,
        DEFAULT_BULK_PAGE_SIZE,
        DEFAULT_CHUNK_OVERLAP,
        DEFAULT_CHUNK_PAGE_SIZE,
        DEFAULT_CHUNK_SIZE,
        DEFAULT_DOCUMENT_PAGE_SIZE,
        DEFAULT_INDEX_TYPE,
        DEFAULT_KB_PAGE_SIZE,
        DEFAULT_TOP_K_DENSE,
        DEFAULT_TOP_K_SPARSE,
        DEFAULT_TOP_M_FINAL,
        DEFAULT_UPLOAD_BATCH_SIZE,
        DEFAULT_UPLOAD_MAX_RETRIES,
        DEFAULT_UPLOAD_TASKS_LIMIT,
        DOCUMENT_FILTER_SOURCE_TYPES,
        DOCUMENT_FILTER_STATUSES,
        DOCUMENT_PAGE_SIZE_OPTIONS,
        FEATURE_BATCH_DELETE,
        FEATURE_BATCH_REBUILD,
        FEATURE_CONSISTENCY_CHECK,
        FEATURE_CONSISTENCY_REPAIR,
        FEATURE_DOCUMENT_REBUILD,
        FEATURE_KB_REBUILD,
        FEATURE_RERANK,
        FEATURE_SPARSE_RETRIEVAL,
        FEATURE_URL_IMPORT,
        MAX_BATCH_DELETE_DOCUMENTS,
        MAX_BATCH_REBUILD_DOCUMENTS,
        MAX_RETRIEVE_TOP_K,
        MAX_UPLOAD_FILE_SIZE,
        MAX_UPLOAD_FILES,
    )
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    route = _build_route_with_manager(MagicMock())

    response = await KnowledgeBaseRoute.get_capabilities(route)

    assert response["status"] == "ok"
    assert response["data"] == {
        "upload": {
            "allowed_extensions": sorted(ALLOWED_UPLOAD_EXTENSIONS),
            "max_file_size_bytes": MAX_UPLOAD_FILE_SIZE,
            "max_files_per_upload": MAX_UPLOAD_FILES,
        },
        "defaults": {
            "chunk_size": DEFAULT_CHUNK_SIZE,
            "chunk_overlap": DEFAULT_CHUNK_OVERLAP,
            "batch_size": DEFAULT_UPLOAD_BATCH_SIZE,
            "tasks_limit": DEFAULT_UPLOAD_TASKS_LIMIT,
            "max_retries": DEFAULT_UPLOAD_MAX_RETRIES,
            "top_k_dense": DEFAULT_TOP_K_DENSE,
            "top_k_sparse": DEFAULT_TOP_K_SPARSE,
            "top_m_final": DEFAULT_TOP_M_FINAL,
            "index_type": DEFAULT_INDEX_TYPE,
        },
        "limits": {
            "max_retrieve_top_k": MAX_RETRIEVE_TOP_K,
            "max_batch_delete_documents": MAX_BATCH_DELETE_DOCUMENTS,
            "max_batch_rebuild_documents": MAX_BATCH_REBUILD_DOCUMENTS,
        },
        "pagination": {
            "document_page_size_options": list(DOCUMENT_PAGE_SIZE_OPTIONS),
            "chunk_page_size_options": list(CHUNK_PAGE_SIZE_OPTIONS),
            "default_kb_page_size": DEFAULT_KB_PAGE_SIZE,
            "default_document_page_size": DEFAULT_DOCUMENT_PAGE_SIZE,
            "default_chunk_page_size": DEFAULT_CHUNK_PAGE_SIZE,
            "bulk_page_size": DEFAULT_BULK_PAGE_SIZE,
        },
        "document_filters": {
            "statuses": list(DOCUMENT_FILTER_STATUSES),
            "source_types": list(DOCUMENT_FILTER_SOURCE_TYPES),
        },
        "features": {
            "sparse_retrieval": FEATURE_SPARSE_RETRIEVAL,
            "rerank": FEATURE_RERANK,
            "url_import": FEATURE_URL_IMPORT,
            "document_rebuild": FEATURE_DOCUMENT_REBUILD,
            "kb_rebuild": FEATURE_KB_REBUILD,
            "consistency_check": FEATURE_CONSISTENCY_CHECK,
            "consistency_repair": FEATURE_CONSISTENCY_REPAIR,
            "batch_delete": FEATURE_BATCH_DELETE,
            "batch_rebuild": FEATURE_BATCH_REBUILD,
        },
    }


def test_validate_upload_file_uses_configured_size_limit_in_message():
    from astrbot.core.knowledge_base.capabilities import MAX_UPLOAD_FILE_SIZE
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    with pytest.raises(ValueError, match="文件超过 .* 限制: too-large.md"):
        KnowledgeBaseRoute._validate_upload_file(
            "too-large.md",
            MAX_UPLOAD_FILE_SIZE + 1,
        )


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
        include_trace=False,
    )


@pytest.mark.asyncio
async def test_retrieve_includes_trace_when_requested():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    trace = {
        "dense": [{"rank": 1, "chunk_id": "chunk-1", "score": 0.9}],
        "sparse": [],
        "fusion": [],
        "rerank": [],
        "final": [],
    }
    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.retrieve = AsyncMock(
        return_value={
            "results": [
                {
                    "chunk_id": "chunk-1",
                    "doc_id": "doc-1",
                    "kb_id": "kb-1",
                    "kb_name": "kb",
                    "doc_name": "doc.md",
                    "chunk_index": 0,
                    "content": "hello",
                    "score": 0.9,
                    "char_count": 5,
                },
            ],
            "trace": trace,
        },
    )
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/retrieve",
        method="POST",
        json={"query": "hello", "kb_ids": ["kb-1"], "top_k": 3, "trace": True},
    ):
        response = await KnowledgeBaseRoute.retrieve(route)

    assert response["status"] == "ok"
    assert response["data"]["trace"] == trace
    kb_manager.retrieve.assert_awaited_once_with(
        query="hello",
        kb_names=None,
        kb_ids=["kb-1"],
        top_m_final=3,
        include_trace=True,
    )


@pytest.mark.asyncio
async def test_retrieve_rejects_invalid_trace_flag():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.retrieve = AsyncMock()
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/retrieve",
        method="POST",
        json={"query": "hello", "kb_ids": ["kb-1"], "trace": "maybe"},
    ):
        response = await KnowledgeBaseRoute.retrieve(route)

    assert response["status"] == "error"
    assert "trace" in response["message"]
    kb_manager.retrieve.assert_not_awaited()


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
async def test_retrieve_rejects_top_k_above_capability_limit():
    from astrbot.core.knowledge_base.capabilities import MAX_RETRIEVE_TOP_K
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.retrieve = AsyncMock()
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/retrieve",
        method="POST",
        json={
            "query": "hello",
            "kb_ids": ["kb-1"],
            "top_k": MAX_RETRIEVE_TOP_K + 1,
        },
    ):
        response = await KnowledgeBaseRoute.retrieve(route)

    assert response["status"] == "error"
    assert str(MAX_RETRIEVE_TOP_K) in response["message"]
    kb_manager.retrieve.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_kbs_uses_capability_default_page_size():
    from astrbot.core.knowledge_base.capabilities import DEFAULT_KB_PAGE_SIZE
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb = MagicMock()
    kb.model_dump.return_value = {"kb_id": "kb-1", "kb_name": "kb"}
    kb_manager = MagicMock()
    kb_manager.list_kbs = AsyncMock(return_value=[kb])
    kb_manager.get_kb = AsyncMock(return_value=MagicMock(init_error=None))
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/list",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.list_kbs(route)

    assert response["status"] == "ok"
    assert response["data"]["page"] == 1
    assert response["data"]["page_size"] == DEFAULT_KB_PAGE_SIZE
    assert response["data"]["total"] == 1


@pytest.mark.asyncio
async def test_list_kbs_returns_requested_page_and_total():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kbs = []
    for index in range(1, 6):
        kb = MagicMock()
        kb.kb_id = f"kb-{index}"
        kb.model_dump.return_value = {
            "kb_id": f"kb-{index}",
            "kb_name": f"kb {index}",
        }
        kbs.append(kb)
    kb_manager = MagicMock()
    kb_manager.list_kbs = AsyncMock(return_value=kbs)
    kb_manager.get_kb = AsyncMock(return_value=MagicMock(init_error=None))
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/list?page=2&page_size=2",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.list_kbs(route)

    assert response["status"] == "ok"
    assert response["data"] == {
        "items": [
            {"kb_id": "kb-3", "kb_name": "kb 3"},
            {"kb_id": "kb-4", "kb_name": "kb 4"},
        ],
        "page": 2,
        "page_size": 2,
        "total": 5,
    }
    kbs[0].model_dump.assert_not_called()
    kbs[1].model_dump.assert_not_called()
    kbs[4].model_dump.assert_not_called()


@pytest.mark.asyncio
async def test_list_kbs_refresh_stats_merges_database_stats():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb = MagicMock()
    kb.kb_id = "kb-1"
    kb.model_dump.return_value = {
        "kb_id": "kb-1",
        "kb_name": "kb",
        "doc_count": 1,
        "chunk_count": 2,
    }
    kb_manager = MagicMock()
    kb_manager.list_kbs = AsyncMock(return_value=[kb])
    kb_manager.get_kb = AsyncMock(return_value=MagicMock(init_error=None))
    kb_db = MagicMock()
    kb_db.get_kb_stats = AsyncMock(
        return_value={
            "kb_id": "kb-1",
            "kb_name": "kb",
            "document_count": 3,
            "ready_document_count": 2,
            "failed_document_count": 1,
            "indexed_chunk_count": 8,
            "document_chunk_count": 9,
            "storage_bytes": 1024,
            "status_counts": {"ready": 2, "failed": 1},
        },
    )
    route = _build_route_with_manager(kb_manager)
    route._get_kb_db = MagicMock(return_value=kb_db)

    async with app.test_request_context(
        "/api/kb/list?refresh_stats=true",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.list_kbs(route)

    assert response["status"] == "ok"
    item = response["data"]["items"][0]
    assert item["document_count"] == 3
    assert item["ready_document_count"] == 2
    assert item["failed_document_count"] == 1
    assert item["indexed_chunk_count"] == 8
    assert item["document_chunk_count"] == 9
    assert item["storage_bytes"] == 1024
    assert item["status_counts"] == {"ready": 2, "failed": 1}
    kb_db.get_kb_stats.assert_awaited_once_with("kb-1")


@pytest.mark.asyncio
async def test_list_kbs_skips_database_stats_without_refresh_flag():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb = MagicMock()
    kb.kb_id = "kb-1"
    kb.model_dump.return_value = {"kb_id": "kb-1", "kb_name": "kb"}
    kb_manager = MagicMock()
    kb_manager.list_kbs = AsyncMock(return_value=[kb])
    kb_manager.get_kb = AsyncMock(return_value=MagicMock(init_error=None))
    kb_db = MagicMock()
    kb_db.get_kb_stats = AsyncMock(return_value={})
    route = _build_route_with_manager(kb_manager)
    route._get_kb_db = MagicMock(return_value=kb_db)

    async with app.test_request_context(
        "/api/kb/list",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.list_kbs(route)

    assert response["status"] == "ok"
    assert response["data"]["items"] == [{"kb_id": "kb-1", "kb_name": "kb"}]
    kb_db.get_kb_stats.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_documents_returns_total_and_uses_requested_pagination():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = MagicMock()
    doc = MagicMock()
    doc.model_dump.return_value = {"doc_id": "doc-1", "doc_name": "alpha.md"}
    kb_helper.list_documents = AsyncMock(return_value=[doc])
    kb_helper.count_documents = AsyncMock(side_effect=[12, 123])
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/document/list?kb_id=kb-1&page=3&page_size=25&search=alpha&status=ready&source_type=file",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.list_documents(route)

    assert response["status"] == "ok"
    assert response["data"]["items"] == [{"doc_id": "doc-1", "doc_name": "alpha.md"}]
    assert response["data"]["page"] == 3
    assert response["data"]["page_size"] == 25
    assert response["data"]["total"] == 12
    assert response["data"]["filtered_total"] == 12
    assert response["data"]["document_count"] == 123
    kb_helper.list_documents.assert_awaited_once_with(
        offset=50,
        limit=25,
        search="alpha",
        status="ready",
        source_type="file",
    )
    assert kb_helper.count_documents.await_args_list[0].kwargs == {
        "search": "alpha",
        "status": "ready",
        "source_type": "file",
    }
    assert kb_helper.count_documents.await_args_list[1].args == ()
    assert kb_helper.count_documents.await_args_list[1].kwargs == {}


@pytest.mark.asyncio
async def test_list_documents_uses_total_as_document_count_without_search():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = MagicMock()
    kb_helper.list_documents = AsyncMock(return_value=[])
    kb_helper.count_documents = AsyncMock(return_value=7)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/document/list?kb_id=kb-1&page=1&page_size=25",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.list_documents(route)

    assert response["status"] == "ok"
    assert response["data"]["total"] == 7
    assert response["data"]["filtered_total"] == 7
    assert response["data"]["document_count"] == 7
    kb_helper.count_documents.assert_awaited_once_with(
        search=None,
        status=None,
        source_type=None,
    )


@pytest.mark.asyncio
async def test_list_documents_uses_capability_default_page_size():
    from astrbot.core.knowledge_base.capabilities import DEFAULT_DOCUMENT_PAGE_SIZE
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = MagicMock()
    kb_helper.list_documents = AsyncMock(return_value=[])
    kb_helper.count_documents = AsyncMock(return_value=7)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/document/list?kb_id=kb-1",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.list_documents(route)

    assert response["status"] == "ok"
    assert response["data"]["page_size"] == DEFAULT_DOCUMENT_PAGE_SIZE
    kb_helper.list_documents.assert_awaited_once_with(
        offset=0,
        limit=DEFAULT_DOCUMENT_PAGE_SIZE,
        search=None,
        status=None,
        source_type=None,
    )


@pytest.mark.asyncio
async def test_list_documents_rejects_invalid_filters():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=MagicMock())
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/document/list?kb_id=kb-1&status=deleted",
        method="GET",
    ):
        invalid_status_response = await KnowledgeBaseRoute.list_documents(route)

    async with app.test_request_context(
        "/api/kb/document/list?kb_id=kb-1&source_type=database",
        method="GET",
    ):
        invalid_source_response = await KnowledgeBaseRoute.list_documents(route)

    assert invalid_status_response["status"] == "error"
    assert "status" in invalid_status_response["message"]
    assert invalid_source_response["status"] == "error"
    assert "source_type" in invalid_source_response["message"]


@pytest.mark.asyncio
async def test_list_chunks_forwards_search_and_total():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = MagicMock()
    kb_helper.search_chunks_by_doc_id = AsyncMock(
        return_value=([{"chunk_id": "c1"}], 7),
    )
    kb_helper.get_chunk_count_by_doc_id = AsyncMock(return_value=42)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/chunk/list?kb_id=kb-1&doc_id=doc-1&page=2&page_size=3&search=hello",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.list_chunks(route)

    assert response["status"] == "ok"
    assert response["data"] == {
        "items": [{"chunk_id": "c1"}],
        "page": 2,
        "page_size": 3,
        "total": 7,
        "filtered_total": 7,
        "document_chunk_count": 42,
    }
    kb_helper.search_chunks_by_doc_id.assert_awaited_once_with(
        doc_id="doc-1",
        search="hello",
        offset=3,
        limit=3,
    )
    kb_helper.get_chunk_count_by_doc_id.assert_awaited_once_with("doc-1")


@pytest.mark.asyncio
async def test_list_chunks_uses_filtered_total_as_document_chunk_count_without_search():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = MagicMock()
    kb_helper.search_chunks_by_doc_id = AsyncMock(
        return_value=([{"chunk_id": "c1"}], 7),
    )
    kb_helper.get_chunk_count_by_doc_id = AsyncMock()
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/chunk/list?kb_id=kb-1&doc_id=doc-1&page=1&page_size=10",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.list_chunks(route)

    assert response["status"] == "ok"
    assert response["data"]["total"] == 7
    assert response["data"]["filtered_total"] == 7
    assert response["data"]["document_chunk_count"] == 7
    kb_helper.get_chunk_count_by_doc_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_chunks_uses_capability_default_page_size():
    from astrbot.core.knowledge_base.capabilities import DEFAULT_CHUNK_PAGE_SIZE
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = MagicMock()
    kb_helper.search_chunks_by_doc_id = AsyncMock(return_value=([], 0))
    kb_helper.get_chunk_count_by_doc_id = AsyncMock()
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/chunk/list?kb_id=kb-1&doc_id=doc-1",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.list_chunks(route)

    assert response["status"] == "ok"
    assert response["data"]["page_size"] == DEFAULT_CHUNK_PAGE_SIZE
    kb_helper.search_chunks_by_doc_id.assert_awaited_once_with(
        doc_id="doc-1",
        search=None,
        offset=0,
        limit=DEFAULT_CHUNK_PAGE_SIZE,
    )


@pytest.mark.asyncio
async def test_get_chunk_context_returns_helper_context():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = MagicMock()
    kb_helper.get_chunk_context = AsyncMock(
        return_value={
            "previous": None,
            "current": {"chunk_id": "chunk-1"},
            "next": {"chunk_id": "chunk-2"},
        },
    )
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/chunk/context?kb_id=kb-1&doc_id=doc-1&chunk_id=chunk-1",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.get_chunk_context(route)

    assert response["status"] == "ok"
    assert response["data"]["current"] == {"chunk_id": "chunk-1"}
    kb_manager.get_kb.assert_awaited_once_with("kb-1")
    kb_helper.get_chunk_context.assert_awaited_once_with(
        chunk_id="chunk-1",
        doc_id="doc-1",
    )


@pytest.mark.asyncio
async def test_get_chunk_context_requires_chunk_id():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/chunk/context?kb_id=kb-1&doc_id=doc-1",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.get_chunk_context(route)

    assert response["status"] == "error"
    assert response["message"] == "缺少参数 chunk_id"
    kb_manager.get_kb.assert_not_called()


@pytest.mark.asyncio
async def test_get_kb_stats_returns_extended_database_stats():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = _build_kb_helper_with_options(kb_id="kb-1", kb_name="kb")
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    kb_db = MagicMock()
    kb_db.get_kb_stats = AsyncMock(
        return_value={
            "kb_id": "kb-1",
            "kb_name": "kb",
            "doc_count": 3,
            "chunk_count": 8,
            "document_count": 3,
            "ready_document_count": 2,
            "failed_document_count": 1,
            "pending_document_count": 0,
            "processing_document_count": 0,
            "indexed_chunk_count": 8,
            "document_chunk_count": 8,
            "media_count": 1,
            "source_file_count": 1,
            "storage_bytes": 17,
            "status_counts": {"ready": 2, "failed": 1},
            "created_at": "2026-06-01T00:00:00+00:00",
            "updated_at": "2026-06-01T00:00:00+00:00",
        },
    )
    kb_manager.kb_db = kb_db
    route = _build_route_with_manager(kb_manager)
    route._get_kb_db = MagicMock(return_value=kb_db)

    async with app.test_request_context(
        "/api/kb/stats?kb_id=kb-1",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.get_kb_stats(route)

    assert response["status"] == "ok"
    assert response["data"]["document_count"] == 3
    assert response["data"]["ready_document_count"] == 2
    assert response["data"]["failed_document_count"] == 1
    assert response["data"]["source_file_count"] == 1
    assert response["data"]["storage_bytes"] == 17
    assert response["data"]["status_counts"] == {"ready": 2, "failed": 1}
    kb_db.get_kb_stats.assert_awaited_once_with("kb-1")


@pytest.mark.asyncio
async def test_get_kb_stats_fallback_keeps_extended_schema():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = _build_kb_helper_with_options(kb_id="kb-1", kb_name="kb")
    kb_helper.kb.doc_count = 3
    kb_helper.kb.chunk_count = 8
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    kb_db = MagicMock()
    kb_db.get_kb_stats = AsyncMock(return_value=None)
    route = _build_route_with_manager(kb_manager)
    route._get_kb_db = MagicMock(return_value=kb_db)

    async with app.test_request_context(
        "/api/kb/stats?kb_id=kb-1",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.get_kb_stats(route)

    assert response["status"] == "ok"
    assert response["data"]["document_count"] == 3
    assert response["data"]["ready_document_count"] == 3
    assert response["data"]["indexed_chunk_count"] == 8
    assert response["data"]["document_chunk_count"] == 8
    assert response["data"]["media_count"] == 0
    assert response["data"]["source_file_count"] == 0
    assert response["data"]["storage_bytes"] == 0
    assert response["data"]["status_counts"] == {"ready": 3}
    kb_db.get_kb_stats.assert_awaited_once_with("kb-1")


@pytest.mark.asyncio
async def test_check_kb_consistency_returns_helper_report():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    report = {
        "kb_id": "kb-1",
        "summary": {"healthy": False, "missing_vectors": 1},
        "issues": {"missing_vectors": [{"doc_id": "doc-1"}]},
    }
    kb_helper = MagicMock()
    kb_helper.check_consistency = AsyncMock(return_value=report)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/consistency/check?kb_id=kb-1",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.check_kb_consistency(route)

    assert response["status"] == "ok"
    assert response["data"] == report
    kb_manager.get_kb.assert_awaited_once_with("kb-1")
    kb_helper.check_consistency.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_check_kb_consistency_requires_existing_kb():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=None)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/consistency/check?kb_id=missing-kb",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.check_kb_consistency(route)

    assert response["status"] == "error"
    assert response["message"] == "知识库不存在"
    kb_manager.get_kb.assert_awaited_once_with("missing-kb")


@pytest.mark.asyncio
async def test_repair_kb_consistency_returns_helper_report():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    report = {
        "kb_id": "kb-1",
        "summary": {"repaired_count": 1, "failed_count": 0},
        "actions": {"repaired": [{"type": "orphan_vectors"}]},
    }
    kb_helper = MagicMock()
    kb_helper.repair_consistency = AsyncMock(return_value=report)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/consistency/repair",
        method="POST",
        json={
            "kb_id": "kb-1",
            "repair_types": ["orphan_vectors"],
        },
    ):
        response = await KnowledgeBaseRoute.repair_kb_consistency(route)

    assert response["status"] == "ok"
    assert response["data"] == report
    kb_manager.get_kb.assert_awaited_once_with("kb-1")
    kb_helper.repair_consistency.assert_awaited_once_with(
        repair_types=["orphan_vectors"],
    )


@pytest.mark.asyncio
async def test_repair_kb_consistency_requires_existing_kb():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=None)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/consistency/repair",
        method="POST",
        json={"kb_id": "missing-kb"},
    ):
        response = await KnowledgeBaseRoute.repair_kb_consistency(route)

    assert response["status"] == "error"
    assert response["message"] == "知识库不存在"
    kb_manager.get_kb.assert_awaited_once_with("missing-kb")


@pytest.mark.asyncio
async def test_repair_kb_consistency_rejects_invalid_repair_types():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock()
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/consistency/repair",
        method="POST",
        json={"kb_id": "kb-1", "repair_types": "orphan_vectors"},
    ):
        response = await KnowledgeBaseRoute.repair_kb_consistency(route)

    assert response["status"] == "error"
    assert response["message"] == "repair_types 格式错误"
    kb_manager.get_kb.assert_not_awaited()


@pytest.mark.asyncio
async def test_repair_kb_consistency_returns_helper_validation_errors():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = MagicMock()
    kb_helper.repair_consistency = AsyncMock(
        side_effect=ValueError("不支持的一致性修复类型: invalid"),
    )
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/consistency/repair",
        method="POST",
        json={"kb_id": "kb-1", "repair_types": ["invalid"]},
    ):
        response = await KnowledgeBaseRoute.repair_kb_consistency(route)

    assert response["status"] == "error"
    assert response["message"] == "不支持的一致性修复类型: invalid"
    kb_helper.repair_consistency.assert_awaited_once_with(
        repair_types=["invalid"],
    )


@pytest.mark.asyncio
async def test_get_upload_progress_falls_back_to_persistent_task():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    route = _build_route_with_manager(MagicMock())
    route.upload_tasks = {}
    route.upload_progress = {}
    route._get_persistent_task = AsyncMock(
        return_value={
            "task_id": "task-1",
            "status": "completed",
            "progress_stage": "embedding",
            "progress_current": 5,
            "progress_total": 5,
            "progress": {"stage": "embedding", "current": 5, "total": 5},
            "result": {"success_count": 1},
            "error": None,
        },
    )

    async with app.test_request_context(
        "/api/kb/document/upload/progress?task_id=task-1",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.get_upload_progress(route)

    assert response["status"] == "ok"
    assert response["data"] == {
        "task_id": "task-1",
        "status": "completed",
        "progress_stage": "embedding",
        "progress_current": 5,
        "progress_total": 5,
        "progress": {"stage": "embedding", "current": 5, "total": 5},
        "result": {"success_count": 1},
    }
    route._get_persistent_task.assert_awaited_once_with("task-1")


@pytest.mark.asyncio
async def test_get_upload_progress_returns_flattened_persistent_progress():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    route = _build_route_with_manager(MagicMock())
    route.upload_tasks = {}
    route.upload_progress = {}
    route._get_persistent_task = AsyncMock(
        return_value={
            "task_id": "task-1",
            "status": "processing",
            "progress_stage": "chunking",
            "progress_current": 2,
            "progress_total": 8,
            "progress": None,
            "result": None,
            "error": None,
        },
    )

    async with app.test_request_context(
        "/api/kb/document/upload/progress?task_id=task-1",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.get_upload_progress(route)

    assert response["status"] == "ok"
    assert response["data"] == {
        "task_id": "task-1",
        "status": "processing",
        "progress_stage": "chunking",
        "progress_current": 2,
        "progress_total": 8,
    }
    route._get_persistent_task.assert_awaited_once_with("task-1")


def test_get_persistent_progress_updates_includes_flattened_fields():
    route = _build_route_with_manager(MagicMock())
    route.upload_progress = {
        "task-1": {
            "status": "completed",
            "stage": "completed",
            "current": 3,
            "total": 3,
        },
    }

    assert route._get_persistent_progress_updates("task-1") == {
        "progress_stage": "completed",
        "progress_current": 3,
        "progress_total": 3,
        "progress": {
            "status": "completed",
            "stage": "completed",
            "current": 3,
            "total": 3,
        },
    }
    assert route._get_persistent_progress_updates("missing-task") == {}


@pytest.mark.asyncio
async def test_get_upload_progress_returns_failed_task_result_from_memory():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    route = _build_route_with_manager(MagicMock())
    result = {
        "task_id": "task-1",
        "uploaded": [],
        "failed": [{"file_name": "same.md", "error": "same.md: duplicate"}],
        "total": 1,
        "success_count": 0,
        "failed_count": 1,
    }
    route.upload_tasks = {
        "task-1": {
            "status": "failed",
            "result": result,
            "error": "same.md: duplicate",
        },
    }
    route.upload_progress = {
        "task-1": {"status": "failed", "stage": "parsing", "current": 0, "total": 100},
    }
    route._cleanup_task = MagicMock()

    async with app.test_request_context(
        "/api/kb/document/upload/progress?task_id=task-1",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.get_upload_progress(route)

    assert response["status"] == "ok"
    assert response["data"] == {
        "task_id": "task-1",
        "status": "failed",
        "result": result,
        "error": "same.md: duplicate",
    }
    route._cleanup_task.assert_called_once_with("task-1")


@pytest.mark.asyncio
async def test_get_upload_progress_returns_failed_persistent_task_result():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    route = _build_route_with_manager(MagicMock())
    route.upload_tasks = {}
    route.upload_progress = {}
    result = {
        "task_id": "task-1",
        "uploaded": [],
        "failed": [{"file_name": "same.md", "error": "same.md: duplicate"}],
        "total": 1,
        "success_count": 0,
        "failed_count": 1,
    }
    route._get_persistent_task = AsyncMock(
        return_value={
            "task_id": "task-1",
            "status": "failed",
            "progress_stage": "parsing",
            "progress_current": 0,
            "progress_total": 100,
            "progress": {"stage": "parsing", "current": 0, "total": 100},
            "result": result,
            "error": "same.md: duplicate",
        },
    )

    async with app.test_request_context(
        "/api/kb/document/upload/progress?task_id=task-1",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.get_upload_progress(route)

    assert response["status"] == "ok"
    assert response["data"] == {
        "task_id": "task-1",
        "status": "failed",
        "progress_stage": "parsing",
        "progress_current": 0,
        "progress_total": 100,
        "progress": {"stage": "parsing", "current": 0, "total": 100},
        "result": result,
        "error": "same.md: duplicate",
    }
    route._get_persistent_task.assert_awaited_once_with("task-1")


@pytest.mark.asyncio
async def test_get_task_returns_persistent_task():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    route = _build_route_with_manager(MagicMock())
    route._get_persistent_task = AsyncMock(
        return_value={"task_id": "task-1", "status": "completed"},
    )

    async with app.test_request_context(
        "/api/kb/task/get?task_id=task-1",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.get_task(route)

    assert response["status"] == "ok"
    assert response["data"] == {"task_id": "task-1", "status": "completed"}
    route._get_persistent_task.assert_awaited_once_with("task-1")


@pytest.mark.asyncio
async def test_get_task_requires_task_id():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    route = _build_route_with_manager(MagicMock())
    route._get_persistent_task = AsyncMock()

    async with app.test_request_context(
        "/api/kb/task/get",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.get_task(route)

    assert response["status"] == "error"
    assert "task_id" in response["message"]
    route._get_persistent_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_tasks_forwards_filters_and_pagination():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_db = MagicMock()
    kb_db.list_ingestion_tasks = AsyncMock(
        return_value=[{"task_id": "task-1", "status": "completed"}],
    )
    kb_db.count_ingestion_tasks = AsyncMock(return_value=76)
    route = _build_route_with_manager(MagicMock())
    route._get_kb_db = MagicMock(return_value=kb_db)

    async with app.test_request_context(
        "/api/kb/task/list?kb_id=kb-1&status=completed&task_type=upload&page=3&page_size=25",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.list_tasks(route)

    assert response["status"] == "ok"
    assert response["data"] == {
        "items": [{"task_id": "task-1", "status": "completed"}],
        "total": 76,
        "page": 3,
        "page_size": 25,
    }
    kb_db.list_ingestion_tasks.assert_awaited_once_with(
        kb_id="kb-1",
        status="completed",
        task_type="upload",
        offset=50,
        limit=25,
    )
    kb_db.count_ingestion_tasks.assert_awaited_once_with(
        kb_id="kb-1",
        status="completed",
        task_type="upload",
    )


@pytest.mark.asyncio
async def test_list_tasks_uses_capability_default_page_size():
    from astrbot.core.knowledge_base.capabilities import DEFAULT_DOCUMENT_PAGE_SIZE
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_db = MagicMock()
    kb_db.list_ingestion_tasks = AsyncMock(return_value=[])
    kb_db.count_ingestion_tasks = AsyncMock(return_value=0)
    route = _build_route_with_manager(MagicMock())
    route._get_kb_db = MagicMock(return_value=kb_db)

    async with app.test_request_context(
        "/api/kb/task/list",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.list_tasks(route)

    assert response["status"] == "ok"
    assert response["data"]["page_size"] == DEFAULT_DOCUMENT_PAGE_SIZE
    kb_db.list_ingestion_tasks.assert_awaited_once_with(
        kb_id=None,
        status=None,
        task_type=None,
        offset=0,
        limit=DEFAULT_DOCUMENT_PAGE_SIZE,
    )


@pytest.mark.asyncio
async def test_rebuild_document_route_forwards_options():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = MagicMock()
    doc = MagicMock()
    doc.model_dump.return_value = {
        "doc_id": "new-doc",
        "parent_doc_id": "old-doc",
        "version": 2,
    }
    kb_helper.rebuild_document = AsyncMock(return_value=doc)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/document/rebuild",
        method="POST",
        json={
            "kb_id": "kb-1",
            "doc_id": "old-doc",
            "chunk_size": 256,
            "chunk_overlap": 32,
            "batch_size": 4,
            "tasks_limit": 2,
            "max_retries": 1,
        },
    ):
        response = await KnowledgeBaseRoute.rebuild_document(route)

    assert response["status"] == "ok"
    assert response["data"]["doc_id"] == "new-doc"
    kb_helper.rebuild_document.assert_awaited_once_with(
        "old-doc",
        chunk_size=256,
        chunk_overlap=32,
        batch_size=4,
        tasks_limit=2,
        max_retries=1,
    )


@pytest.mark.asyncio
async def test_rebuild_document_route_can_start_background_task():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = MagicMock()
    kb_helper.rebuild_document = AsyncMock()
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)
    route.upload_tasks = {}
    route.upload_progress = {}
    route._create_persistent_task = AsyncMock()
    background_call = object()
    route._background_rebuild_document_task = MagicMock(return_value=background_call)

    with (
        patch(
            "astrbot.dashboard.routes.knowledge_base.uuid.uuid4",
            return_value="task-1",
        ),
        patch(
            "astrbot.dashboard.routes.knowledge_base.asyncio.create_task"
        ) as create_task,
    ):
        async with app.test_request_context(
            "/api/kb/document/rebuild",
            method="POST",
            json={
                "kb_id": "kb-1",
                "doc_id": "old-doc",
                "chunk_size": 256,
                "chunk_overlap": 32,
                "batch_size": 4,
                "tasks_limit": 2,
                "max_retries": 1,
                "background": True,
            },
        ):
            response = await KnowledgeBaseRoute.rebuild_document(route)

    assert response["status"] == "ok"
    assert response["data"] == {
        "task_id": "task-1",
        "doc_id": "old-doc",
        "message": "document rebuild task created, processing in background",
    }
    assert route.upload_tasks["task-1"]["status"] == "pending"
    route._create_persistent_task.assert_awaited_once_with(
        task_id="task-1",
        kb_id="kb-1",
        task_type="document_rebuild",
        status="pending",
        progress={
            "status": "pending",
            "file_index": 0,
            "file_total": 1,
            "file_name": "old-doc",
            "stage": "waiting",
            "current": 0,
            "total": 100,
        },
    )
    route._background_rebuild_document_task.assert_called_once_with(
        task_id="task-1",
        kb_helper=kb_helper,
        doc_id="old-doc",
        chunk_size=256,
        chunk_overlap=32,
        batch_size=4,
        tasks_limit=2,
        max_retries=1,
    )
    create_task.assert_called_once_with(background_call)
    kb_helper.rebuild_document.assert_not_awaited()


@pytest.mark.asyncio
async def test_rebuild_document_route_rejects_invalid_background_flag():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock()
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/document/rebuild",
        method="POST",
        json={
            "kb_id": "kb-1",
            "doc_id": "doc-1",
            "background": "later",
        },
    ):
        response = await KnowledgeBaseRoute.rebuild_document(route)

    assert response["status"] == "error"
    assert "background" in response["message"]
    kb_manager.get_kb.assert_not_awaited()


@pytest.mark.asyncio
async def test_rebuild_document_route_rejects_invalid_options():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock()
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/document/rebuild",
        method="POST",
        json={
            "kb_id": "kb-1",
            "doc_id": "doc-1",
            "chunk_size": 10,
            "chunk_overlap": 10,
        },
    ):
        response = await KnowledgeBaseRoute.rebuild_document(route)

    assert response["status"] == "error"
    assert "chunk_overlap" in response["message"]
    kb_manager.get_kb.assert_not_awaited()


@pytest.mark.asyncio
async def test_rebuild_kb_route_forwards_options():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = MagicMock()
    kb_helper.rebuild_all_documents = AsyncMock(
        return_value={
            "total": 1,
            "success_count": 1,
            "failed_count": 0,
            "rebuilt": [{"doc_id": "doc-new"}],
            "failed": [],
        },
    )
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/rebuild",
        method="POST",
        json={
            "kb_id": "kb-1",
            "chunk_size": 256,
            "chunk_overlap": 32,
            "batch_size": 4,
            "tasks_limit": 2,
            "max_retries": 1,
        },
    ):
        response = await KnowledgeBaseRoute.rebuild_kb(route)

    assert response["status"] == "ok"
    assert response["data"]["success_count"] == 1
    kb_helper.rebuild_all_documents.assert_awaited_once_with(
        chunk_size=256,
        chunk_overlap=32,
        batch_size=4,
        tasks_limit=2,
        max_retries=1,
    )


@pytest.mark.asyncio
async def test_rebuild_kb_route_can_start_background_task():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = _build_kb_helper_with_options(kb_id="kb-1", kb_name="docs")
    kb_helper.rebuild_all_documents = AsyncMock()
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)
    route.upload_tasks = {}
    route.upload_progress = {}
    route._create_persistent_task = AsyncMock()
    background_call = object()
    route._background_rebuild_kb_task = MagicMock(return_value=background_call)

    with (
        patch(
            "astrbot.dashboard.routes.knowledge_base.uuid.uuid4",
            return_value="task-1",
        ),
        patch(
            "astrbot.dashboard.routes.knowledge_base.asyncio.create_task"
        ) as create_task,
    ):
        async with app.test_request_context(
            "/api/kb/rebuild",
            method="POST",
            json={
                "kb_id": "kb-1",
                "chunk_size": 256,
                "chunk_overlap": 32,
                "batch_size": 4,
                "tasks_limit": 2,
                "max_retries": 1,
                "background": True,
            },
        ):
            response = await KnowledgeBaseRoute.rebuild_kb(route)

    assert response["status"] == "ok"
    assert response["data"] == {
        "task_id": "task-1",
        "kb_id": "kb-1",
        "message": "knowledge base rebuild task created, processing in background",
    }
    assert route.upload_tasks["task-1"]["status"] == "pending"
    route._create_persistent_task.assert_awaited_once_with(
        task_id="task-1",
        kb_id="kb-1",
        task_type="kb_rebuild",
        status="pending",
        progress={
            "status": "pending",
            "file_index": 0,
            "file_total": 1,
            "file_name": "docs",
            "stage": "waiting",
            "current": 0,
            "total": 100,
        },
    )
    route._background_rebuild_kb_task.assert_called_once_with(
        task_id="task-1",
        kb_helper=kb_helper,
        chunk_size=256,
        chunk_overlap=32,
        batch_size=4,
        tasks_limit=2,
        max_retries=1,
    )
    create_task.assert_called_once_with(background_call)
    kb_helper.rebuild_all_documents.assert_not_awaited()


@pytest.mark.asyncio
async def test_rebuild_kb_route_requires_kb_id():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock()
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/rebuild",
        method="POST",
        json={},
    ):
        response = await KnowledgeBaseRoute.rebuild_kb(route)

    assert response["status"] == "error"
    assert "kb_id" in response["message"]
    kb_manager.get_kb.assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_rebuild_documents_route_starts_background_task():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = MagicMock()
    kb_helper.rebuild_documents = AsyncMock()
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)
    route.upload_tasks = {}
    route.upload_progress = {}
    route._create_persistent_task = AsyncMock()
    background_call = object()
    route._background_rebuild_documents_task = MagicMock(
        return_value=background_call,
    )

    with (
        patch(
            "astrbot.dashboard.routes.knowledge_base.uuid.uuid4",
            return_value="task-1",
        ),
        patch(
            "astrbot.dashboard.routes.knowledge_base.asyncio.create_task"
        ) as create_task,
    ):
        async with app.test_request_context(
            "/api/kb/document/batch-rebuild",
            method="POST",
            json={
                "kb_id": "kb-1",
                "doc_ids": ["doc-1", "doc-2", "doc-1"],
                "chunk_size": 256,
                "chunk_overlap": 32,
                "batch_size": 4,
                "tasks_limit": 2,
                "max_retries": 1,
            },
        ):
            response = await KnowledgeBaseRoute.batch_rebuild_documents(route)

    assert response["status"] == "ok"
    assert response["data"] == {
        "task_id": "task-1",
        "doc_ids": ["doc-1", "doc-2"],
        "message": "document batch rebuild task created, processing in background",
    }
    assert route.upload_tasks["task-1"]["status"] == "pending"
    route._create_persistent_task.assert_awaited_once_with(
        task_id="task-1",
        kb_id="kb-1",
        task_type="document_batch_rebuild",
        status="pending",
        progress={
            "status": "pending",
            "file_index": 0,
            "file_total": 2,
            "file_name": "2 selected documents",
            "stage": "waiting",
            "current": 0,
            "total": 2,
        },
    )
    route._background_rebuild_documents_task.assert_called_once_with(
        task_id="task-1",
        kb_helper=kb_helper,
        doc_ids=["doc-1", "doc-2"],
        chunk_size=256,
        chunk_overlap=32,
        batch_size=4,
        tasks_limit=2,
        max_retries=1,
    )
    create_task.assert_called_once_with(background_call)
    kb_helper.rebuild_documents.assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_rebuild_documents_route_rejects_invalid_doc_ids():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock()
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/document/batch-rebuild",
        method="POST",
        json={"kb_id": "kb-1", "doc_ids": []},
    ):
        response = await KnowledgeBaseRoute.batch_rebuild_documents(route)

    assert response["status"] == "error"
    assert "doc_ids" in response["message"]
    kb_manager.get_kb.assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_rebuild_documents_route_rejects_limit_excess():
    from astrbot.core.knowledge_base.capabilities import MAX_BATCH_REBUILD_DOCUMENTS
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock()
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/document/batch-rebuild",
        method="POST",
        json={
            "kb_id": "kb-1",
            "doc_ids": [
                f"doc-{index}" for index in range(MAX_BATCH_REBUILD_DOCUMENTS + 1)
            ],
        },
    ):
        response = await KnowledgeBaseRoute.batch_rebuild_documents(route)

    assert response["status"] == "error"
    assert str(MAX_BATCH_REBUILD_DOCUMENTS) in response["message"]
    kb_manager.get_kb.assert_not_awaited()
