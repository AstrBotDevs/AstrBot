import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from astrbot.core.provider.provider import EmbeddingProvider, RerankProvider
from astrbot.dashboard.services.knowledge_base_service import (
    KnowledgeBaseService,
    KnowledgeBaseServiceError,
)


def _make_service(*, kb_manager=None) -> KnowledgeBaseService:
    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    service.knowledge_base_manager = kb_manager or MagicMock()
    service.upload_progress = {}
    service.upload_tasks = {}
    service._background_tasks = set()
    return service


class _EmbeddingProviderStub(EmbeddingProvider):
    def __init__(self, vectors: list[float], dim: int):
        super().__init__({}, {})
        self._vectors = vectors
        self._dim = dim

    async def get_embedding(self, text: str) -> list[float]:
        return self._vectors

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        return [self._vectors for _ in text]

    def get_dim(self) -> int:
        return self._dim


class _RerankProviderStub(RerankProvider):
    def __init__(self, results):
        super().__init__({}, {})
        self._results = results

    async def rerank(self, query: str, documents: list[str], top_n: int | None = None):
        return self._results


@pytest.mark.asyncio
async def test_background_upload_task_aggregates_uploaded_and_failed_documents(
    tmp_path,
):
    uploaded_doc = MagicMock()
    uploaded_doc.model_dump.return_value = {"doc_id": "doc-1", "doc_name": "ok.txt"}
    kb_helper = AsyncMock()
    kb_helper.upload_document = AsyncMock(
        side_effect=[uploaded_doc, RuntimeError("embedding failed")]
    )
    service = _make_service()
    staging_dir = tmp_path / "task-upload"
    staging_dir.mkdir()
    ok_file = staging_dir / "ok.txt"
    bad_file = staging_dir / "bad.md"
    ok_file.write_bytes(b"ok")
    bad_file.write_bytes(b"bad")

    await service.background_upload_task(
        task_id="task-upload",
        kb_helper=kb_helper,
        files_to_upload=[
            {
                "file_name": "ok.txt",
                "temp_file_path": ok_file,
                "file_type": "txt",
            },
            {
                "file_name": "bad.md",
                "temp_file_path": bad_file,
                "file_type": "md",
            },
        ],
        staging_dir=staging_dir,
        chunk_size=256,
        chunk_overlap=32,
        batch_size=8,
        tasks_limit=2,
        max_retries=5,
    )

    assert service.upload_tasks["task-upload"]["status"] == "completed"
    assert service.upload_progress["task-upload"]["status"] == "completed"
    assert service.upload_tasks["task-upload"]["result"] == {
        "task_id": "task-upload",
        "uploaded": [{"doc_id": "doc-1", "doc_name": "ok.txt"}],
        "failed": [{"file_name": "bad.md", "error": "bad.md: Document upload failed"}],
        "total": 2,
        "success_count": 1,
        "failed_count": 1,
    }
    assert kb_helper.upload_document.await_count == 2
    first_call = kb_helper.upload_document.await_args_list[0]
    assert first_call.kwargs["file_name"] == "ok.txt"
    assert first_call.kwargs["file_content"] == b"ok"
    assert first_call.kwargs["chunk_size"] == 256
    assert first_call.kwargs["chunk_overlap"] == 32
    assert callable(first_call.kwargs["progress_callback"])
    assert not staging_dir.exists()


@pytest.mark.asyncio
async def test_background_upload_task_marks_failed_when_file_shape_breaks_outer_flow(
    tmp_path,
):
    kb_helper = AsyncMock()
    service = _make_service()
    staging_dir = tmp_path / "task-upload-broken"
    staging_dir.mkdir()

    await service.background_upload_task(
        task_id="task-upload-broken",
        kb_helper=kb_helper,
        files_to_upload=[{"file_name": "broken.txt", "file_type": "txt"}],
        staging_dir=staging_dir,
        chunk_size=256,
        chunk_overlap=32,
        batch_size=8,
        tasks_limit=2,
        max_retries=5,
    )

    assert service.upload_tasks["task-upload-broken"]["status"] == "failed"
    assert (
        service.upload_tasks["task-upload-broken"]["error"]
        == "Knowledge base task failed"
    )
    assert service.upload_progress["task-upload-broken"]["status"] == "failed"
    kb_helper.upload_document.assert_not_awaited()
    assert not staging_dir.exists()


@pytest.mark.asyncio
async def test_background_import_task_aggregates_failures_and_infers_file_types():
    uploaded_doc = MagicMock()
    uploaded_doc.model_dump.return_value = {"doc_id": "doc-1", "doc_name": "guide.md"}
    kb_helper = AsyncMock()
    kb_helper.upload_document = AsyncMock(
        side_effect=[uploaded_doc, RuntimeError("chunk validation failed")]
    )
    service = _make_service()

    await service.background_import_task(
        task_id="task-import",
        kb_helper=kb_helper,
        documents=[
            {"file_name": "guide.md", "chunks": ["part 1", "part 2"]},
            {"file_name": "plain-text", "chunks": ["bad"]},
        ],
        batch_size=16,
        tasks_limit=4,
        max_retries=6,
    )

    assert service.upload_tasks["task-import"]["status"] == "completed"
    assert service.upload_progress["task-import"]["status"] == "completed"
    assert service.upload_tasks["task-import"]["result"] == {
        "task_id": "task-import",
        "uploaded": [{"doc_id": "doc-1", "doc_name": "guide.md"}],
        "failed": [
            {
                "file_name": "plain-text",
                "error": "plain-text: Document upload failed",
            }
        ],
        "total": 2,
        "success_count": 1,
        "failed_count": 1,
    }
    assert kb_helper.upload_document.await_count == 2
    first_call = kb_helper.upload_document.await_args_list[0]
    second_call = kb_helper.upload_document.await_args_list[1]
    assert first_call.kwargs["file_type"] == "md"
    assert first_call.kwargs["pre_chunked_text"] == ["part 1", "part 2"]
    assert second_call.kwargs["file_type"] == "txt"
    assert second_call.kwargs["pre_chunked_text"] == ["bad"]
    assert callable(second_call.kwargs["progress_callback"])


@pytest.mark.asyncio
async def test_background_import_task_marks_failed_when_document_shape_breaks_outer_flow():
    kb_helper = AsyncMock()
    service = _make_service()

    await service.background_import_task(
        task_id="task-import-broken",
        kb_helper=kb_helper,
        documents=[object()],
        batch_size=16,
        tasks_limit=4,
        max_retries=6,
    )

    assert service.upload_tasks["task-import-broken"]["status"] == "failed"
    assert (
        service.upload_tasks["task-import-broken"]["error"]
        == "Knowledge base task failed"
    )
    assert service.upload_progress["task-import-broken"]["status"] == "failed"
    kb_helper.upload_document.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_kb_rejects_invalid_rerank_provider():
    provider_manager = MagicMock()
    provider_manager.get_provider_by_id = AsyncMock(
        side_effect=[_EmbeddingProviderStub([0.1, 0.2], 2), object()]
    )
    kb_manager = MagicMock(provider_manager=provider_manager)
    service = _make_service(kb_manager=kb_manager)

    with pytest.raises(KnowledgeBaseServiceError, match="重排序模型不存在"):
        await service.create_kb(
            {
                "kb_name": "demo",
                "embedding_provider_id": "embed-1",
                "rerank_provider_id": "rerank-1",
            }
        )


@pytest.mark.asyncio
async def test_create_kb_wraps_empty_rerank_validation_result():
    provider_manager = MagicMock()
    provider_manager.get_provider_by_id = AsyncMock(
        side_effect=[
            _EmbeddingProviderStub([0.1, 0.2], 2),
            _RerankProviderStub([]),
        ]
    )
    kb_manager = MagicMock(provider_manager=provider_manager)
    service = _make_service(kb_manager=kb_manager)

    with pytest.raises(KnowledgeBaseServiceError, match="测试重排序模型失败"):
        await service.create_kb(
            {
                "kb_name": "demo",
                "embedding_provider_id": "embed-1",
                "rerank_provider_id": "rerank-1",
            }
        )


@pytest.mark.asyncio
async def test_create_kb_delegates_with_validated_providers():
    provider_manager = MagicMock()
    provider_manager.get_provider_by_id = AsyncMock(
        side_effect=[
            _EmbeddingProviderStub([0.1, 0.2], 2),
            _RerankProviderStub([{"index": 0, "score": 0.9}]),
        ]
    )
    created_helper = MagicMock()
    created_helper.kb.model_dump.return_value = {"kb_id": "kb-1", "kb_name": "Demo"}
    kb_manager = MagicMock(
        provider_manager=provider_manager,
        create_kb=AsyncMock(return_value=created_helper),
    )
    service = _make_service(kb_manager=kb_manager)

    result, message = await service.create_kb(
        {
            "kb_name": "Demo",
            "description": "desc",
            "emoji": "📚",
            "embedding_provider_id": "embed-1",
            "rerank_provider_id": "rerank-1",
            "chunk_size": 512,
            "chunk_overlap": 64,
            "top_k_dense": 8,
            "top_k_sparse": 6,
            "top_m_final": 4,
        }
    )

    assert result == {"kb_id": "kb-1", "kb_name": "Demo"}
    assert message == "创建知识库成功"
    assert provider_manager.get_provider_by_id.await_args_list == [
        call("embed-1"),
        call("rerank-1"),
    ]
    kb_manager.create_kb.assert_awaited_once_with(
        kb_name="Demo",
        description="desc",
        emoji="📚",
        embedding_provider_id="embed-1",
        rerank_provider_id="rerank-1",
        chunk_size=512,
        chunk_overlap=64,
        top_k_dense=8,
        top_k_sparse=6,
        top_m_final=4,
    )


@pytest.mark.asyncio
async def test_import_documents_schedules_background_task(monkeypatch):
    kb_helper = AsyncMock()
    kb_manager = MagicMock(get_kb=AsyncMock(return_value=kb_helper))
    service = _make_service(kb_manager=kb_manager)
    scheduled_tasks: list[asyncio.Task] = []
    scheduled_calls: list[dict] = []

    async def fake_background_import_task(**kwargs):
        scheduled_calls.append(kwargs)

    def fake_create_task(task_set, coro, *, name=None):
        task = asyncio.get_running_loop().create_task(coro)
        task_set.add(task)
        scheduled_tasks.append(task)
        return task

    monkeypatch.setattr(service, "background_import_task", fake_background_import_task)
    monkeypatch.setattr(
        "astrbot.dashboard.services.knowledge_base_service.create_tracked_task",
        fake_create_task,
    )

    result = await service.import_documents(
        {
            "kb_id": "kb-1",
            "documents": [{"file_name": "doc.txt", "chunks": ["part 1"]}],
            "batch_size": 10,
            "tasks_limit": 4,
            "max_retries": 7,
        }
    )
    await asyncio.gather(*scheduled_tasks)

    assert result["doc_count"] == 1
    assert result["task_id"] in service.upload_tasks
    assert service.upload_tasks[result["task_id"]]["status"] == "pending"
    assert scheduled_calls == [
        {
            "task_id": result["task_id"],
            "kb_helper": kb_helper,
            "documents": [{"file_name": "doc.txt", "chunks": ["part 1"]}],
            "batch_size": 10,
            "tasks_limit": 4,
            "max_retries": 7,
        }
    ]


@pytest.mark.asyncio
async def test_upload_document_from_url_schedules_background_task(monkeypatch):
    kb_helper = AsyncMock()
    kb_manager = MagicMock(get_kb=AsyncMock(return_value=kb_helper))
    service = _make_service(kb_manager=kb_manager)
    scheduled_tasks: list[asyncio.Task] = []
    scheduled_calls: list[dict] = []

    async def fake_background_upload_from_url_task(**kwargs):
        scheduled_calls.append(kwargs)

    def fake_create_task(task_set, coro, *, name=None):
        task = asyncio.get_running_loop().create_task(coro)
        task_set.add(task)
        scheduled_tasks.append(task)
        return task

    monkeypatch.setattr(
        service,
        "background_upload_from_url_task",
        fake_background_upload_from_url_task,
    )
    monkeypatch.setattr(
        "astrbot.dashboard.services.knowledge_base_service.create_tracked_task",
        fake_create_task,
    )

    result = await service.upload_document_from_url(
        {
            "kb_id": "kb-1",
            "url": "https://example.com/doc",
            "chunk_size": 1024,
            "chunk_overlap": 80,
            "batch_size": 16,
            "tasks_limit": 5,
            "max_retries": 6,
            "enable_cleaning": True,
            "cleaning_provider_id": "cleaner-1",
        }
    )
    await asyncio.gather(*scheduled_tasks)

    assert result["url"] == "https://example.com/doc"
    assert result["task_id"] in service.upload_tasks
    assert service.upload_tasks[result["task_id"]]["status"] == "pending"
    assert scheduled_calls == [
        {
            "task_id": result["task_id"],
            "kb_helper": kb_helper,
            "url": "https://example.com/doc",
            "chunk_size": 1024,
            "chunk_overlap": 80,
            "batch_size": 16,
            "tasks_limit": 5,
            "max_retries": 6,
            "enable_cleaning": True,
            "cleaning_provider_id": "cleaner-1",
        }
    ]


@pytest.mark.asyncio
async def test_list_kbs_clamps_pagination_and_includes_init_error():
    first_kb = MagicMock(kb_id="kb-1")
    first_kb.model_dump.return_value = {"kb_id": "kb-1", "kb_name": "First"}
    second_kb = MagicMock(kb_id="kb-2")
    second_kb.model_dump.return_value = {"kb_id": "kb-2", "kb_name": "Second"}
    kb_helper = MagicMock(init_error="index load failed")
    kb_manager = MagicMock(
        list_kbs=AsyncMock(return_value=[first_kb, second_kb]),
        get_kb=AsyncMock(return_value=kb_helper),
    )
    service = _make_service(kb_manager=kb_manager)

    result = await service.list_kbs(page=0, page_size=0)

    assert result == {
        "items": [
            {
                "kb_id": "kb-1",
                "kb_name": "First",
                "init_error": "Knowledge base initialization failed",
            }
        ],
        "page": 1,
        "page_size": 1,
        "total": 2,
    }
    kb_manager.get_kb.assert_awaited_once_with("kb-1")


@pytest.mark.asyncio
async def test_update_kb_rejects_missing_identifier_and_empty_updates():
    service = _make_service()

    with pytest.raises(KnowledgeBaseServiceError, match="缺少参数 kb_id"):
        await service.update_kb({"description": "desc"})

    with pytest.raises(KnowledgeBaseServiceError, match="至少需要提供一个更新字段"):
        await service.update_kb({"kb_id": "kb-1"})


@pytest.mark.asyncio
async def test_update_kb_uses_existing_name_when_payload_omits_it():
    current_kb = MagicMock()
    current_kb.kb.kb_name = "Current Name"
    current_kb.kb.description = None
    current_kb.kb.emoji = None
    current_kb.kb.embedding_provider_id = None
    current_kb.kb.rerank_provider_id = None
    current_kb.kb.chunk_size = None
    current_kb.kb.chunk_overlap = None
    current_kb.kb.top_k_dense = None
    current_kb.kb.top_k_sparse = None
    current_kb.kb.top_m_final = None
    updated_kb = MagicMock()
    updated_kb.kb.model_dump.return_value = {"kb_id": "kb-1", "kb_name": "Current Name"}
    kb_manager = MagicMock(
        get_kb=AsyncMock(return_value=current_kb),
        update_kb=AsyncMock(return_value=updated_kb),
    )
    service = _make_service(kb_manager=kb_manager)

    result, message = await service.update_kb(
        {"kb_id": "kb-1", "description": "updated"}
    )

    assert result == {"kb_id": "kb-1", "kb_name": "Current Name"}
    assert message == "更新知识库成功"
    kb_manager.update_kb.assert_awaited_once_with(
        kb_id="kb-1",
        kb_name="Current Name",
        description="updated",
        emoji=None,
        embedding_provider_id=None,
        rerank_provider_id=None,
        chunk_size=None,
        chunk_overlap=None,
        top_k_dense=None,
        top_k_sparse=None,
        top_m_final=None,
    )


@pytest.mark.asyncio
async def test_update_kb_rejects_missing_current_or_updated_kb():
    missing_current_manager = MagicMock(
        get_kb=AsyncMock(return_value=None),
        update_kb=AsyncMock(),
    )
    service = _make_service(kb_manager=missing_current_manager)

    with pytest.raises(KnowledgeBaseServiceError, match="知识库不存在"):
        await service.update_kb({"kb_id": "kb-1", "description": "updated"})

    missing_updated_manager = MagicMock(
        get_kb=AsyncMock(return_value=MagicMock(kb=MagicMock(kb_name="Current Name"))),
        update_kb=AsyncMock(return_value=None),
    )
    service = _make_service(kb_manager=missing_updated_manager)

    with pytest.raises(KnowledgeBaseServiceError, match="知识库不存在"):
        await service.update_kb({"kb_id": "kb-1", "kb_name": "Renamed"})


@pytest.mark.asyncio
async def test_list_documents_clamps_pagination_and_trims_search():
    doc = MagicMock()
    doc.model_dump.return_value = {"doc_id": "doc-1", "file_name": "guide.md"}
    kb_helper = MagicMock(
        list_documents=AsyncMock(return_value=[doc]),
        count_documents=AsyncMock(return_value=3),
    )
    kb_manager = MagicMock(get_kb=AsyncMock(return_value=kb_helper))
    service = _make_service(kb_manager=kb_manager)

    result = await service.list_documents(
        kb_id="kb-1",
        page=0,
        page_size=0,
        search="  guide  ",
    )

    assert result == {
        "items": [{"doc_id": "doc-1", "file_name": "guide.md"}],
        "page": 1,
        "page_size": 1,
        "total": 3,
    }
    kb_helper.list_documents.assert_awaited_once_with(offset=0, limit=1, search="guide")
    kb_helper.count_documents.assert_awaited_once_with(search="guide")


@pytest.mark.parametrize(
    ("task_id", "tasks", "message"),
    [
        (None, {}, "缺少参数 task_id"),
        ("missing", {}, "找不到该任务"),
    ],
)
def test_get_upload_progress_rejects_missing_or_unknown_task(task_id, tasks, message):
    service = _make_service()
    service.upload_tasks = tasks

    with pytest.raises(KnowledgeBaseServiceError, match=message):
        service.get_upload_progress(task_id)


def test_get_upload_progress_returns_state_specific_fields():
    service = _make_service()
    service.upload_tasks = {
        "processing-task": {"status": "processing", "result": None, "error": None},
        "completed-task": {
            "status": "completed",
            "result": {"uploaded": [{"doc_id": "doc-1"}]},
            "error": None,
        },
        "failed-task": {
            "status": "failed",
            "result": None,
            "error": "network error",
        },
    }
    service.upload_progress = {
        "processing-task": {
            "status": "processing",
            "stage": "embedding",
            "current": 2,
            "total": 5,
        }
    }

    assert service.get_upload_progress("processing-task") == {
        "task_id": "processing-task",
        "status": "processing",
        "progress": {
            "status": "processing",
            "stage": "embedding",
            "current": 2,
            "total": 5,
        },
    }
    assert service.get_upload_progress("completed-task") == {
        "task_id": "completed-task",
        "status": "completed",
        "result": {"uploaded": [{"doc_id": "doc-1"}]},
    }
    assert service.get_upload_progress("failed-task") == {
        "task_id": "failed-task",
        "status": "failed",
        "error": "network error",
    }


@pytest.mark.asyncio
async def test_retrieve_rejects_invalid_request_shapes():
    service = _make_service()

    with pytest.raises(KnowledgeBaseServiceError, match="缺少参数 query"):
        await service.retrieve({"kb_names": ["demo"]})

    with pytest.raises(KnowledgeBaseServiceError, match="缺少参数 kb_names 或格式错误"):
        await service.retrieve({"query": "astrbot", "kb_names": "demo"})


@pytest.mark.asyncio
async def test_retrieve_redacts_debug_visualization_errors(monkeypatch):
    kb_manager = MagicMock(retrieve=AsyncMock(return_value=None))
    service = _make_service(kb_manager=kb_manager)
    sensitive_error = (
        "api_key=top-secret Bearer token-123 password=dashboard-password "
        "https://internal.example/visualization C:\\private\\secret.txt"
    )
    logged_errors: list[tuple[object, ...]] = []

    class RecordingLogger:
        def error(self, *args: object) -> None:
            logged_errors.append(args)

    async def fake_generate_tsne_visualization(query, kb_names, manager):
        assert query == "astrbot"
        assert kb_names == ["demo"]
        assert manager is kb_manager
        raise RuntimeError(sensitive_error)

    monkeypatch.setattr(
        "astrbot.dashboard.services.knowledge_base_service.generate_tsne_visualization",
        fake_generate_tsne_visualization,
    )
    monkeypatch.setattr(
        "astrbot.dashboard.services.knowledge_base_service.logger",
        RecordingLogger(),
    )

    result = await service.retrieve(
        {"query": "astrbot", "kb_names": ["demo"], "top_k": 3, "debug": True}
    )

    assert result == {
        "results": [],
        "total": 0,
        "query": "astrbot",
        "visualization_error": "Visualization generation failed",
    }
    rendered_logs = " ".join(str(args) for args in logged_errors)
    for fragment in (
        "top-secret",
        "token-123",
        "dashboard-password",
        "internal.example",
        "C:\\private\\secret.txt",
    ):
        assert fragment not in rendered_logs
    kb_manager.retrieve.assert_awaited_once_with(
        query="astrbot",
        kb_names=["demo"],
        top_m_final=3,
    )


@pytest.mark.asyncio
async def test_background_upload_from_url_task_records_completed_result():
    uploaded_doc = MagicMock()
    uploaded_doc.model_dump.return_value = {"doc_id": "doc-1", "file_name": "page.md"}
    kb_helper = MagicMock(upload_from_url=AsyncMock(return_value=uploaded_doc))
    service = _make_service()

    await service.background_upload_from_url_task(
        task_id="url-task",
        kb_helper=kb_helper,
        url="https://example.com/doc",
        chunk_size=512,
        chunk_overlap=32,
        batch_size=8,
        tasks_limit=3,
        max_retries=5,
        enable_cleaning=True,
        cleaning_provider_id="cleaner-1",
    )

    assert service.upload_tasks["url-task"] == {
        "status": "completed",
        "result": {
            "task_id": "url-task",
            "uploaded": [{"doc_id": "doc-1", "file_name": "page.md"}],
            "failed": [],
            "total": 1,
            "success_count": 1,
            "failed_count": 0,
        },
        "error": None,
    }
    assert service.upload_progress["url-task"]["status"] == "completed"
    kb_helper.upload_from_url.assert_awaited_once()
    upload_call = kb_helper.upload_from_url.await_args
    assert upload_call.kwargs["url"] == "https://example.com/doc"
    assert upload_call.kwargs["enable_cleaning"] is True
    assert upload_call.kwargs["cleaning_provider_id"] == "cleaner-1"
    assert callable(upload_call.kwargs["progress_callback"])


@pytest.mark.asyncio
async def test_background_upload_from_url_task_records_failures():
    kb_helper = MagicMock(
        upload_from_url=AsyncMock(side_effect=RuntimeError("download failed"))
    )
    service = _make_service()

    await service.background_upload_from_url_task(
        task_id="url-task-failed",
        kb_helper=kb_helper,
        url="https://example.com/doc",
        chunk_size=512,
        chunk_overlap=32,
        batch_size=8,
        tasks_limit=3,
        max_retries=5,
        enable_cleaning=False,
        cleaning_provider_id=None,
    )

    assert service.upload_tasks["url-task-failed"] == {
        "status": "failed",
        "result": None,
        "error": "Knowledge base task failed",
    }
    assert service.upload_progress["url-task-failed"]["status"] == "failed"


@pytest.mark.asyncio
async def test_get_kb_validates_identifier_and_missing_kb():
    kb_manager = MagicMock(get_kb=AsyncMock(return_value=None))
    service = _make_service(kb_manager=kb_manager)

    with pytest.raises(KnowledgeBaseServiceError, match="缺少参数 kb_id"):
        await service.get_kb(None)

    with pytest.raises(KnowledgeBaseServiceError, match="知识库不存在"):
        await service.get_kb("kb-1")


@pytest.mark.asyncio
async def test_get_kb_stats_returns_serialized_counts_and_timestamps():
    now = datetime(2026, 7, 3, 8, 30, tzinfo=UTC)
    kb = MagicMock(
        kb_id="kb-1",
        kb_name="Demo",
        doc_count=4,
        chunk_count=9,
        created_at=now,
        updated_at=now,
    )
    kb_helper = MagicMock(kb=kb)
    kb_manager = MagicMock(get_kb=AsyncMock(return_value=kb_helper))
    service = _make_service(kb_manager=kb_manager)

    result = await service.get_kb_stats("kb-1")

    assert result == {
        "kb_id": "kb-1",
        "kb_name": "Demo",
        "doc_count": 4,
        "chunk_count": 9,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }


@pytest.mark.asyncio
async def test_get_kb_stats_rejects_missing_or_unknown_kb():
    kb_manager = MagicMock(get_kb=AsyncMock(return_value=None))
    service = _make_service(kb_manager=kb_manager)

    with pytest.raises(KnowledgeBaseServiceError, match="缺少参数 kb_id"):
        await service.get_kb_stats(None)

    with pytest.raises(KnowledgeBaseServiceError, match="知识库不存在"):
        await service.get_kb_stats("kb-1")


@pytest.mark.asyncio
async def test_delete_kb_validates_identifier_and_missing_kb():
    kb_manager = MagicMock(delete_kb=AsyncMock(return_value=False))
    service = _make_service(kb_manager=kb_manager)

    with pytest.raises(KnowledgeBaseServiceError, match="缺少参数 kb_id"):
        await service.delete_kb({})

    with pytest.raises(KnowledgeBaseServiceError, match="知识库不存在"):
        await service.delete_kb({"kb_id": "kb-1"})


@pytest.mark.asyncio
async def test_delete_kb_returns_success_message():
    kb_manager = MagicMock(delete_kb=AsyncMock(return_value=True))
    service = _make_service(kb_manager=kb_manager)

    result, message = await service.delete_kb({"kb_id": "kb-1"})

    assert result is None
    assert message == "删除知识库成功"
    kb_manager.delete_kb.assert_awaited_once_with("kb-1")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "缺少参数 kb_id"),
        ({"kb_id": "kb-1"}, "缺少参数 documents 或格式错误"),
        (
            {"kb_id": "kb-1", "documents": [object()]},
            "文档格式错误，必须包含 file_name 和 chunks",
        ),
        (
            {"kb_id": "kb-1", "documents": [{"file_name": "doc.txt", "chunks": "bad"}]},
            "chunks 必须是列表",
        ),
        (
            {
                "kb_id": "kb-1",
                "documents": [{"file_name": "doc.txt", "chunks": ["ok", "  "]}],
            },
            "chunks 必须是非空字符串列表",
        ),
    ],
)
def test_validate_import_request_rejects_malformed_payloads(payload, message):
    with pytest.raises(KnowledgeBaseServiceError, match=message):
        KnowledgeBaseService.validate_import_request(payload)


def test_validate_import_request_returns_defaults_and_values():
    result = KnowledgeBaseService.validate_import_request(
        {"kb_id": "kb-1", "documents": [{"file_name": "doc.txt", "chunks": ["one"]}]}
    )

    assert result == (
        "kb-1",
        [{"file_name": "doc.txt", "chunks": ["one"]}],
        32,
        3,
        3,
    )


@pytest.mark.asyncio
async def test_upload_document_rejects_invalid_input_shapes():
    service = _make_service()

    with pytest.raises(
        KnowledgeBaseServiceError, match="Content-Type 须为 multipart/form-data"
    ):
        await service.upload_document(
            content_type="application/json",
            form_data={},
            files=[],
        )

    with pytest.raises(KnowledgeBaseServiceError, match="缺少参数 kb_id"):
        await service.upload_document(
            content_type="multipart/form-data",
            form_data={},
            files=[MagicMock(filename="doc.txt")],
        )

    with pytest.raises(KnowledgeBaseServiceError, match="缺少文件"):
        await service.upload_document(
            content_type="multipart/form-data",
            form_data={"kb_id": "kb-1"},
            files=[],
        )


@pytest.mark.asyncio
async def test_upload_document_rejects_missing_kb_after_staging_files(
    monkeypatch, tmp_path
):
    async def fake_save_upload_to_path(file, path):
        path.write_bytes(file.content)

    monkeypatch.setattr(
        "astrbot.dashboard.services.knowledge_base_service.save_upload_to_path",
        fake_save_upload_to_path,
    )
    monkeypatch.setattr(
        "astrbot.dashboard.services.knowledge_base_service.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )

    kb_manager = MagicMock(get_kb=AsyncMock(return_value=None))
    service = _make_service(kb_manager=kb_manager)
    file = MagicMock(filename="guide.md", content=b"content")

    with pytest.raises(KnowledgeBaseServiceError, match="知识库不存在"):
        await service.upload_document(
            content_type="multipart/form-data",
            form_data={"kb_id": "kb-1"},
            files=[file],
        )


@pytest.mark.asyncio
async def test_upload_document_schedules_background_task_with_sanitized_files(
    monkeypatch, tmp_path
):
    kb_helper = AsyncMock()
    kb_manager = MagicMock(get_kb=AsyncMock(return_value=kb_helper))
    service = _make_service(kb_manager=kb_manager)
    scheduled_tasks: list[asyncio.Task] = []
    scheduled_calls: list[dict] = []

    async def fake_save_upload_to_path(file, path):
        path.write_bytes(file.content)

    async def fake_background_upload_task(**kwargs):
        scheduled_calls.append(kwargs)

    def fake_create_task(task_set, coro, *, name=None):
        task = asyncio.get_running_loop().create_task(coro)
        task_set.add(task)
        scheduled_tasks.append(task)
        return task

    monkeypatch.setattr(
        "astrbot.dashboard.services.knowledge_base_service.save_upload_to_path",
        fake_save_upload_to_path,
    )
    monkeypatch.setattr(
        "astrbot.dashboard.services.knowledge_base_service.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )
    monkeypatch.setattr(service, "background_upload_task", fake_background_upload_task)
    monkeypatch.setattr(
        "astrbot.dashboard.services.knowledge_base_service.create_tracked_task",
        fake_create_task,
    )

    result = await service.upload_document(
        content_type="multipart/form-data; boundary=test",
        form_data={
            "kb_id": "kb-1",
            "chunk_size": "1024",
            "chunk_overlap": "80",
            "batch_size": "16",
            "tasks_limit": "5",
            "max_retries": "6",
        },
        files=[
            MagicMock(filename="nested\\guide.md", content=b"guide"),
            MagicMock(filename="..", content=b"fallback"),
        ],
    )
    await asyncio.gather(*scheduled_tasks)

    assert result["file_count"] == 2
    assert result["task_id"] in service.upload_tasks
    assert service.upload_tasks[result["task_id"]]["status"] == "pending"
    assert len(scheduled_calls) == 1
    scheduled_call = scheduled_calls[0]
    assert scheduled_call["task_id"] == result["task_id"]
    assert scheduled_call["kb_helper"] is kb_helper
    assert scheduled_call["chunk_size"] == 1024
    assert scheduled_call["chunk_overlap"] == 80
    assert scheduled_call["batch_size"] == 16
    assert scheduled_call["tasks_limit"] == 5
    assert scheduled_call["max_retries"] == 6

    staging_dir = scheduled_call["staging_dir"]
    assert staging_dir.parent == tmp_path
    assert staging_dir.name == f"kb_upload_{result['task_id']}"
    assert [
        {key: file_info[key] for key in ("file_name", "file_type")}
        for file_info in scheduled_call["files_to_upload"]
    ] == [
        {"file_name": "guide.md", "file_type": "md"},
        {"file_name": "document", "file_type": ""},
    ]
    assert [
        file_info["temp_file_path"].read_bytes()
        for file_info in scheduled_call["files_to_upload"]
    ] == [b"guide", b"fallback"]


@pytest.mark.asyncio
async def test_get_document_validates_inputs_and_missing_entities():
    kb_manager = MagicMock(get_kb=AsyncMock(return_value=None))
    service = _make_service(kb_manager=kb_manager)

    with pytest.raises(KnowledgeBaseServiceError, match="缺少参数 kb_id"):
        await service.get_document(kb_id=None, doc_id="doc-1")

    with pytest.raises(KnowledgeBaseServiceError, match="缺少参数 doc_id"):
        await service.get_document(kb_id="kb-1", doc_id=None)

    with pytest.raises(KnowledgeBaseServiceError, match="知识库不存在"):
        await service.get_document(kb_id="kb-1", doc_id="doc-1")

    kb_helper = MagicMock(get_document=AsyncMock(return_value=None))
    kb_manager = MagicMock(get_kb=AsyncMock(return_value=kb_helper))
    service = _make_service(kb_manager=kb_manager)

    with pytest.raises(KnowledgeBaseServiceError, match="文档不存在"):
        await service.get_document(kb_id="kb-1", doc_id="doc-1")


@pytest.mark.asyncio
async def test_get_document_returns_model_dump():
    document = MagicMock()
    document.model_dump.return_value = {"doc_id": "doc-1", "file_name": "guide.md"}
    kb_helper = MagicMock(get_document=AsyncMock(return_value=document))
    kb_manager = MagicMock(get_kb=AsyncMock(return_value=kb_helper))
    service = _make_service(kb_manager=kb_manager)

    result = await service.get_document(kb_id="kb-1", doc_id="doc-1")

    assert result == {"doc_id": "doc-1", "file_name": "guide.md"}


@pytest.mark.asyncio
async def test_delete_document_and_chunk_validate_inputs_and_delegate():
    kb_helper = MagicMock(
        delete_document=AsyncMock(),
        delete_chunk=AsyncMock(),
    )
    kb_manager = MagicMock(get_kb=AsyncMock(return_value=kb_helper))
    service = _make_service(kb_manager=kb_manager)

    with pytest.raises(KnowledgeBaseServiceError, match="缺少参数 kb_id"):
        await service.delete_document({"doc_id": "doc-1"})

    with pytest.raises(KnowledgeBaseServiceError, match="缺少参数 doc_id"):
        await service.delete_document({"kb_id": "kb-1"})

    missing_service = _make_service(
        kb_manager=MagicMock(get_kb=AsyncMock(return_value=None))
    )
    with pytest.raises(KnowledgeBaseServiceError, match="知识库不存在"):
        await missing_service.delete_document({"kb_id": "kb-1", "doc_id": "doc-1"})

    result, message = await service.delete_document(
        {"kb_id": "kb-1", "doc_id": "doc-1"}
    )
    assert result is None
    assert message == "删除文档成功"
    kb_helper.delete_document.assert_awaited_once_with("doc-1")

    with pytest.raises(KnowledgeBaseServiceError, match="缺少参数 chunk_id"):
        await service.delete_chunk({"kb_id": "kb-1", "doc_id": "doc-1"})

    with pytest.raises(KnowledgeBaseServiceError, match="缺少参数 doc_id"):
        await service.delete_chunk({"kb_id": "kb-1", "chunk_id": "chunk-1"})

    result, message = await service.delete_chunk(
        {"kb_id": "kb-1", "chunk_id": "chunk-1", "doc_id": "doc-1"}
    )
    assert result is None
    assert message == "删除文本块成功"
    kb_helper.delete_chunk.assert_awaited_once_with("chunk-1", "doc-1")


@pytest.mark.asyncio
async def test_list_chunks_validates_kb_and_doc_and_delegates():
    kb_helper = MagicMock(
        get_chunks_by_doc_id=AsyncMock(return_value=[{"chunk_id": "chunk-1"}]),
        get_chunk_count_by_doc_id=AsyncMock(return_value=7),
    )
    kb_manager = MagicMock(get_kb=AsyncMock(return_value=kb_helper))
    service = _make_service(kb_manager=kb_manager)

    with pytest.raises(KnowledgeBaseServiceError, match="缺少参数 kb_id"):
        await service.list_chunks(kb_id=None, doc_id="doc-1", page=1, page_size=5)

    with pytest.raises(KnowledgeBaseServiceError, match="缺少参数 doc_id"):
        await service.list_chunks(kb_id="kb-1", doc_id=None, page=1, page_size=5)

    missing_service = _make_service(
        kb_manager=MagicMock(get_kb=AsyncMock(return_value=None))
    )
    with pytest.raises(KnowledgeBaseServiceError, match="知识库不存在"):
        await missing_service.list_chunks(
            kb_id="kb-1", doc_id="doc-1", page=1, page_size=5
        )

    result = await service.list_chunks(
        kb_id="kb-1", doc_id="doc-1", page=2, page_size=5
    )

    assert result == {
        "items": [{"chunk_id": "chunk-1"}],
        "page": 2,
        "page_size": 5,
        "total": 7,
    }
    kb_helper.get_chunks_by_doc_id.assert_awaited_once_with(
        doc_id="doc-1",
        offset=5,
        limit=5,
    )
    kb_helper.get_chunk_count_by_doc_id.assert_awaited_once_with("doc-1")
