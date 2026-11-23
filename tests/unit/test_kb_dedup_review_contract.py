"""Behavior checks for the legacy and service knowledge base adapters."""

import asyncio
import copy
from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from quart import Quart
from werkzeug.datastructures import FileStorage

from astrbot.core.provider.provider import EmbeddingProvider
from astrbot.dashboard.routes import knowledge_base as route_module
from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute
from astrbot.dashboard.routes.route import RouteContext
from astrbot.dashboard.services import knowledge_base_service as service_module
from astrbot.dashboard.services.knowledge_base_service import (
    KnowledgeBaseService,
    KnowledgeBaseServiceError,
)


class LocalEmbeddingProvider(EmbeddingProvider):
    """Provide a real provider type without an external embedding request."""

    def __init__(self):
        super().__init__({}, {})

    async def get_embedding(self, text: str) -> list[float]:
        return [0.25, 0.75]

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        return [[0.25, 0.75] for _ in text]

    def get_dim(self) -> int:
        return 2


def make_kb(kb_id: str = "kb-1"):
    """Create stable metadata with a fresh serialized dictionary per call."""
    return SimpleNamespace(
        kb_id=kb_id,
        kb_name="Docs",
        description="description",
        emoji="book",
        embedding_provider_id="embedding-1",
        rerank_provider_id="rerank-1",
        chunk_size=512,
        chunk_overlap=50,
        top_k_dense=50,
        top_k_sparse=50,
        top_m_final=5,
        doc_count=2,
        chunk_count=4,
        created_at=datetime(2024, 1, 2, tzinfo=UTC),
        updated_at=datetime(2024, 1, 3, tzinfo=UTC),
        model_dump=lambda: {"kb_id": kb_id, "kb_name": "Docs"},
    )


@pytest.fixture
def kb_adapters():
    kb = make_kb()
    helper = SimpleNamespace(
        kb=kb,
        init_error=None,
        list_documents=AsyncMock(return_value=[]),
        get_document=AsyncMock(return_value=None),
        delete_document=AsyncMock(),
        delete_chunk=AsyncMock(),
        upload_from_url=AsyncMock(),
    )
    manager = SimpleNamespace(
        get_kb=AsyncMock(return_value=helper),
        list_kbs=AsyncMock(return_value=[kb]),
        create_kb=AsyncMock(return_value=helper),
        update_kb=AsyncMock(return_value=helper),
        delete_kb=AsyncMock(return_value=True),
        provider_manager=SimpleNamespace(
            get_provider_by_id=AsyncMock(return_value=LocalEmbeddingProvider())
        ),
    )
    lifecycle = SimpleNamespace(kb_manager=manager)
    app = Quart(__name__)
    app.testing = True
    route = KnowledgeBaseRoute(RouteContext(config={}, app=app), lifecycle)
    return SimpleNamespace(
        route=route,
        service=KnowledgeBaseService(lifecycle),
        manager=manager,
        helper=helper,
        client=app.test_client(),
    )


@pytest.mark.asyncio
async def test_list_adapters_preserve_their_pagination_and_init_error(kb_adapters):
    h = kb_adapters
    h.manager.list_kbs.return_value = [make_kb("first"), make_kb("second")]
    h.manager.get_kb.side_effect = lambda kb_id: SimpleNamespace(
        init_error="embedding unavailable" if kb_id == "first" else None
    )
    response = await h.client.get("/api/kb/list?page=2&page_size=1")
    assert response.status_code == 200
    assert await response.get_json() == {
        "status": "ok",
        "message": None,
        "data": {
            "items": [
                {
                    "kb_id": "first",
                    "kb_name": "Docs",
                    "init_error": "embedding unavailable",
                },
                {"kb_id": "second", "kb_name": "Docs"},
            ],
            "page": 2,
            "page_size": 1,
        },
    }
    assert await h.service.list_kbs(page=2, page_size=1) == {
        "items": [{"kb_id": "second", "kb_name": "Docs"}],
        "page": 2,
        "page_size": 1,
        "total": 2,
    }


@pytest.mark.asyncio
async def test_legacy_create_passes_all_optional_settings(kb_adapters):
    h = kb_adapters
    response = await h.client.post(
        "/api/kb/create",
        json={"kb_name": "Docs", "embedding_provider_id": "embedding-1"},
    )
    assert (await response.get_json())["message"] == "创建知识库成功"
    h.manager.create_kb.assert_awaited_once_with(
        kb_name="Docs",
        description=None,
        emoji=None,
        embedding_provider_id="embedding-1",
        rerank_provider_id=None,
        chunk_size=None,
        chunk_overlap=None,
        top_k_dense=None,
        top_k_sparse=None,
        top_m_final=None,
    )


@pytest.mark.asyncio
async def test_legacy_update_keeps_none_defaults(kb_adapters):
    h = kb_adapters
    response = await h.client.post(
        "/api/kb/update", json={"kb_id": "kb-1", "chunk_size": 1024}
    )
    assert (await response.get_json())["message"] == "更新知识库成功"
    h.manager.update_kb.assert_awaited_once_with(
        kb_id="kb-1",
        kb_name=None,
        description=None,
        emoji=None,
        embedding_provider_id=None,
        rerank_provider_id=None,
        chunk_size=1024,
        chunk_overlap=None,
        top_k_dense=None,
        top_k_sparse=None,
        top_m_final=None,
    )


@pytest.mark.asyncio
async def test_legacy_update_rejects_an_all_none_update(kb_adapters):
    response = await kb_adapters.client.post(
        "/api/kb/update", json={"kb_id": "kb-1", "rerank_provider_id": None}
    )
    assert (await response.get_json())["message"] == "至少需要提供一个更新字段"
    kb_adapters.manager.update_kb.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_document_list_keeps_unclamped_pagination(kb_adapters):
    response = await kb_adapters.client.get(
        "/api/kb/document/list?kb_id=kb-1&page=0&page_size=-5"
    )
    assert (await response.get_json())["data"] == {
        "items": [],
        "page": 0,
        "page_size": -5,
    }
    kb_adapters.helper.list_documents.assert_awaited_once_with(offset=5, limit=-5)


@pytest.mark.asyncio
async def test_legacy_stats_preserves_metadata_response(kb_adapters):
    response = await kb_adapters.client.get("/api/kb/stats?kb_id=kb-1")
    assert (await response.get_json())["data"] == {
        "kb_id": "kb-1",
        "kb_name": "Docs",
        "doc_count": 2,
        "chunk_count": 4,
        "created_at": "2024-01-02T00:00:00+00:00",
        "updated_at": "2024-01-03T00:00:00+00:00",
    }


@pytest.mark.parametrize(
    ("path", "payload", "message"),
    [
        ("/api/kb/delete", {}, "缺少参数 kb_id"),
        ("/api/kb/document/delete", {"kb_id": "absent"}, "缺少参数 doc_id"),
        (
            "/api/kb/chunk/delete",
            {"kb_id": "absent", "doc_id": "doc-1"},
            "缺少参数 chunk_id",
        ),
        (
            "/api/kb/chunk/delete",
            {"kb_id": "absent", "chunk_id": "chunk-1"},
            "缺少参数 doc_id",
        ),
        ("/api/kb/document/upload/url", {"kb_id": "absent"}, "缺少参数 url"),
    ],
)
@pytest.mark.asyncio
async def test_legacy_required_fields_precede_kb_lookup(
    kb_adapters, path, payload, message
):
    h = kb_adapters
    h.manager.get_kb.return_value = None
    response = await h.client.post(path, json=payload)
    assert response.status_code == 200
    assert await response.get_json() == {
        "status": "error",
        "message": message,
        "data": {},
    }
    h.manager.get_kb.assert_not_awaited()


@pytest.mark.parametrize(
    "path", ["/api/kb/get", "/api/kb/stats", "/api/kb/document/list"]
)
@pytest.mark.asyncio
async def test_legacy_query_kb_errors_keep_the_envelope(kb_adapters, path):
    h = kb_adapters
    h.manager.get_kb.return_value = None
    for query, message in [("", "缺少参数 kb_id"), ("?kb_id=absent", "知识库不存在")]:
        response = await h.client.get(path + query)
        assert response.status_code == 200
        assert await response.get_json() == {
            "status": "error",
            "message": message,
            "data": {},
        }
    h.manager.get_kb.assert_awaited_once_with("absent")


@pytest.mark.asyncio
async def test_legacy_truthy_identifier_contract_is_separate_from_service(kb_adapters):
    h = kb_adapters
    response = await h.client.post("/api/kb/delete", json={"kb_id": 7})
    assert (await response.get_json())["message"] == "删除知识库成功"
    h.manager.delete_kb.assert_awaited_once_with(7)
    h.manager.delete_kb.reset_mock()
    with pytest.raises(KnowledgeBaseServiceError, match="^缺少参数 kb_id$"):
        await h.service.delete_kb({"kb_id": 7})
    h.manager.delete_kb.assert_not_awaited()


@pytest.mark.parametrize(
    ("method", "payload", "message"),
    [
        ("delete_document", {"kb_id": True, "doc_id": "doc"}, "缺少参数 kb_id"),
        ("delete_document", {"kb_id": "absent", "doc_id": 5}, "缺少参数 doc_id"),
        ("delete_chunk", {"kb_id": "absent"}, "缺少参数 chunk_id"),
        (
            "delete_chunk",
            {"kb_id": "absent", "chunk_id": "chunk"},
            "缺少参数 doc_id",
        ),
        ("upload_document_from_url", {"kb_id": "absent", "url": 4}, "缺少参数 url"),
    ],
)
@pytest.mark.asyncio
async def test_service_identifier_errors_keep_validation_order(
    kb_adapters, method, payload, message
):
    h = kb_adapters
    h.manager.get_kb.return_value = None
    with pytest.raises(KnowledgeBaseServiceError, match=f"^{message}$"):
        await getattr(h.service, method)(payload)
    h.manager.get_kb.assert_not_awaited()


@pytest.mark.asyncio
async def test_multipart_integer_errors_precede_missing_kb(kb_adapters):
    h = kb_adapters
    response = await h.client.post(
        "/api/kb/document/upload",
        form={"kb_id": "", "chunk_size": "bad"},
        files={"file": FileStorage(BytesIO(b"content"), filename="sample.txt")},
    )
    message = "invalid literal for int() with base 10: 'bad'"
    assert (await response.get_json())["message"] == message
    with pytest.raises(ValueError) as error:
        await h.service.upload_document(
            content_type="multipart/form-data",
            form_data={"kb_id": "", "chunk_size": "bad"},
            files={},
        )
    assert str(error.value) == message
    h.manager.get_kb.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_upload_still_rejects_more_than_ten_files(kb_adapters):
    h = kb_adapters
    response = await h.client.post(
        "/api/kb/document/upload",
        form={"kb_id": "kb-1"},
        files={
            f"file{index}": FileStorage(BytesIO(b"content"), filename=f"{index}.txt")
            for index in range(11)
        },
    )
    assert (await response.get_json())["message"] == "最多只能上传10个文件"
    h.manager.get_kb.assert_not_awaited()
    assert h.route.upload_tasks == {}


@pytest.mark.parametrize(
    "state", ["pending", "processing", "completed", "failed", "other"]
)
@pytest.mark.asyncio
async def test_progress_projection_keeps_state_specific_fields(kb_adapters, state):
    task = {"status": state, "result": {"uploaded": ["doc"]}, "error": "failure"}
    progress = {"file_index": 0, "file_name": "", "current": 0, "total": 2}
    h = kb_adapters
    for adapter in [h.route, h.service]:
        adapter.upload_tasks["task"] = copy.deepcopy(task)
        adapter.upload_progress["task"] = copy.deepcopy(progress)
    expected = {"task_id": "task", "status": state}
    if state == "processing":
        expected["progress"] = progress
    elif state == "completed":
        expected["result"] = {"uploaded": ["doc"]}
    elif state == "failed":
        expected["error"] = "failure"
    response = await h.client.get("/api/kb/document/upload/progress?task_id=task")
    assert (await response.get_json())["data"] == expected
    assert h.service.get_upload_progress("task") == expected
    for adapter in [h.route, h.service]:
        assert adapter.upload_tasks == {"task": task}
        assert adapter.upload_progress == {"task": progress}


@pytest.mark.parametrize("adapter_name", ["route", "service"])
@pytest.mark.asyncio
async def test_progress_callbacks_preserve_zero_values_and_ignore_unknown_tasks(
    kb_adapters, adapter_name
):
    adapter = getattr(kb_adapters, adapter_name)
    prefix = "_" if adapter_name == "route" else ""
    update = getattr(adapter, prefix + "update_progress")
    update("unknown", status="processing", current=0)
    assert adapter.upload_progress == {}
    adapter.upload_progress["task"] = {"status": "pending", "current": 9}
    callback = getattr(adapter, prefix + "make_progress_callback")("task", 0, "")
    await callback("", 0, 0)
    assert adapter.upload_progress["task"] == {
        "status": "processing",
        "file_index": 0,
        "file_name": "",
        "stage": "",
        "current": 0,
        "total": 0,
    }
    unchanged = copy.deepcopy(adapter.upload_progress)
    update("task")
    assert adapter.upload_progress == unchanged


@pytest.mark.parametrize("adapter_name", ["route", "service"])
@pytest.mark.asyncio
async def test_url_upload_scheduling_and_completion_preserve_arguments(
    kb_adapters, adapter_name, monkeypatch
):
    h = kb_adapters
    adapter = getattr(h, adapter_name)
    module = route_module if adapter_name == "route" else service_module
    tasks = []

    def schedule(coroutine):
        task = asyncio.create_task(coroutine)
        tasks.append(task)
        return task

    monkeypatch.setattr(module, "asyncio", SimpleNamespace(create_task=schedule))
    h.helper.upload_from_url.return_value = SimpleNamespace(
        model_dump=lambda: {"doc_id": "doc-1"}
    )
    payload = {
        "kb_id": "kb-1",
        "url": "https://example.invalid/local-test",
        "chunk_size": 64,
        "chunk_overlap": 2,
        "batch_size": 4,
        "tasks_limit": 1,
        "max_retries": 2,
    }
    try:
        if adapter_name == "route":
            response = await h.client.post("/api/kb/document/upload/url", json=payload)
            data = (await response.get_json())["data"]
        else:
            data = await adapter.upload_document_from_url(payload)
        assert data["url"] == payload["url"]
        assert data["message"] == "URL upload task created, processing in background"
        assert len(tasks) == 1
        await tasks[0]
        arguments = dict(h.helper.upload_from_url.await_args.kwargs)
        assert callable(arguments.pop("progress_callback"))
        assert arguments == {
            "url": "https://example.invalid/local-test",
            "chunk_size": 64,
            "chunk_overlap": 2,
            "batch_size": 4,
            "tasks_limit": 1,
            "max_retries": 2,
            "enable_cleaning": False,
            "cleaning_provider_id": None,
        }
        assert adapter.upload_tasks[data["task_id"]] == {
            "status": "completed",
            "result": {
                "task_id": data["task_id"],
                "uploaded": [{"doc_id": "doc-1"}],
                "failed": [],
                "total": 1,
                "success_count": 1,
                "failed_count": 0,
            },
            "error": None,
        }
    finally:
        await asyncio.gather(*tasks)
