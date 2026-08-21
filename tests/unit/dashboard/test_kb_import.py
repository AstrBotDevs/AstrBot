import asyncio
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from starlette.datastructures import UploadFile

from astrbot.core.exceptions import KnowledgeBaseUploadError
from astrbot.core.knowledge_base.kb_helper import KBHelper
from astrbot.core.knowledge_base.models import KBDocument
from astrbot.core.provider.provider import EmbeddingProvider
from astrbot.dashboard.api.auth import AuthContext
from astrbot.dashboard.api.knowledge_bases import require_kb_scope, router
from astrbot.dashboard.services import knowledge_base_service
from astrbot.dashboard.services.knowledge_base_service import (
    KnowledgeBaseService,
    KnowledgeBaseServiceError,
)


@pytest.fixture
def kb_helper() -> AsyncMock:
    """Return a deterministic knowledge-base helper for route tests."""
    helper = AsyncMock(spec=KBHelper)
    helper.upload_document.return_value = KBDocument(
        doc_id="test_doc_id",
        kb_id="test_kb_id",
        doc_name="test_file.txt",
        file_type="txt",
        file_size=100,
        file_path="",
        chunk_count=2,
        media_count=0,
    )
    return helper


@pytest.fixture
def knowledge_base_route_service(kb_helper: AsyncMock) -> KnowledgeBaseService:
    """Return a service wired only to the controlled KB helper."""
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    return KnowledgeBaseService(kb_manager)


@pytest.fixture
def app(knowledge_base_route_service: KnowledgeBaseService) -> FastAPI:
    """Create a minimal authenticated KB API app without runtime side effects."""
    app = FastAPI()
    app.state.services = SimpleNamespace(knowledge_bases=knowledge_base_route_service)

    async def allow_kb_scope() -> AuthContext:
        return AuthContext(
            username="test",
            scopes=["kb"],
            subject="test-session",
        )

    app.dependency_overrides[require_kb_scope] = allow_kb_scope
    app.include_router(router, prefix="/api/v1")
    return app


@pytest_asyncio.fixture
async def asgi_client(app: FastAPI):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_import_documents(
    asgi_client: httpx.AsyncClient,
    kb_helper: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
):
    """Tests the import documents functionality."""
    kb_helper.upload_document.reset_mock()
    kb_helper.upload_document.side_effect = None

    created_tasks: list[asyncio.Task] = []
    original_create_tracked_task = knowledge_base_service.create_tracked_task

    def capture_background_task(task_set, coroutine, *, name=None):
        task = original_create_tracked_task(task_set, coroutine, name=name)
        created_tasks.append(task)
        return task

    monkeypatch.setattr(
        "astrbot.dashboard.services.knowledge_base_service.create_tracked_task",
        capture_background_task,
    )

    # Test data
    import_data = {
        "documents": [
            {"file_name": "test_file_1.txt", "chunks": ["chunk1", "chunk2"]},
            {"file_name": "test_file_2.md", "chunks": ["chunk3", "chunk4", "chunk5"]},
        ],
    }

    # Send request
    response = await asgi_client.post(
        "/api/v1/knowledge-bases/test_kb_id/documents/import",
        json=import_data,
    )

    # Verify response
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "task_id" in data["data"]
    assert data["data"]["doc_count"] == 2

    task_id = data["data"]["task_id"]

    assert len(created_tasks) == 1
    await asyncio.wait_for(created_tasks[0], timeout=1)
    progress_response = await asgi_client.get(
        f"/api/v1/knowledge-bases/tasks/{task_id}",
    )
    progress_data = progress_response.json()

    assert progress_data["data"]["status"] == "completed"
    result = progress_data["data"]["result"]
    assert result["success_count"] == 2
    assert result["failed_count"] == 0

    # Verify kb_helper.upload_document was called correctly
    assert kb_helper.upload_document.call_count == 2

    # Check first call arguments
    call_args_list = kb_helper.upload_document.call_args_list

    # First document
    args1, kwargs1 = call_args_list[0]
    assert kwargs1["file_name"] == "test_file_1.txt"
    assert kwargs1["pre_chunked_text"] == ["chunk1", "chunk2"]

    # Second document
    args2, kwargs2 = call_args_list[1]
    assert kwargs2["file_name"] == "test_file_2.md"
    assert kwargs2["pre_chunked_text"] == ["chunk3", "chunk4", "chunk5"]


@pytest.mark.asyncio
async def test_import_documents_returns_friendly_failure_message(
    kb_helper: AsyncMock,
):
    kb_helper.upload_document.reset_mock()
    kb_helper.upload_document.side_effect = KnowledgeBaseUploadError(
        stage="embedding",
        user_message=(
            "向量化失败：嵌入模型返回的向量数量与文本分块数量不一致（期望 2，实际 1）。"
        ),
        details={"expected_contents": 2, "actual_vectors": 1},
    )

    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    service.upload_progress = {}
    service.upload_tasks = {}

    await KnowledgeBaseService.background_import_task(
        service,
        task_id="task-1",
        kb_helper=kb_helper,
        documents=[{"file_name": "broken.txt", "chunks": ["chunk1", "chunk2"]}],
        batch_size=32,
        tasks_limit=3,
        max_retries=3,
    )

    assert service.upload_tasks["task-1"]["status"] == "completed"
    result = service.upload_tasks["task-1"]["result"]
    assert result["success_count"] == 0
    assert result["failed_count"] == 1
    assert result["failed"][0]["file_name"] == "broken.txt"
    assert result["failed"][0]["error"].startswith("broken.txt:")
    assert "向量化失败" in result["failed"][0]["error"]
    assert "期望 2，实际 1" in result["failed"][0]["error"]
    assert "not same nb of vectors as ids" not in result["failed"][0]["error"]
    assert kb_helper.upload_document.await_count == 1

    kb_helper.upload_document.side_effect = None


@pytest.mark.asyncio
async def test_import_documents_invalid_input(
    asgi_client: httpx.AsyncClient,
):
    """Tests import documents with invalid input."""
    # Missing documents
    response = await asgi_client.post(
        "/api/v1/knowledge-bases/test_kb/documents/import",
        json={},
    )
    data = response.json()
    assert data["status"] == "error"
    assert "缺少参数 documents" in data["message"]

    # Invalid document format
    response = await asgi_client.post(
        "/api/v1/knowledge-bases/test_kb/documents/import",
        json={
            "documents": [{"file_name": "test"}],  # Missing chunks
        },
    )
    data = response.json()
    assert data["status"] == "error"
    assert "文档格式错误" in data["message"]

    # Invalid chunks type
    response = await asgi_client.post(
        "/api/v1/knowledge-bases/test_kb/documents/import",
        json={
            "documents": [{"file_name": "test", "chunks": "not-a-list"}],
        },
    )
    data = response.json()
    assert data["status"] == "error"
    assert "chunks 必须是列表" in data["message"]

    # Invalid chunks content
    response = await asgi_client.post(
        "/api/v1/knowledge-bases/test_kb/documents/import",
        json={
            "documents": [{"file_name": "test", "chunks": ["valid", ""]}],
        },
    )
    data = response.json()
    assert data["status"] == "error"
    assert "chunks 必须是非空字符串列表" in data["message"]


def _make_service_with_mock_kb_helper():
    """Create a KnowledgeBaseService whose kb_manager returns a mock kb_helper.

    Returns:
        Tuple of (service, kb_helper).
    """
    from unittest.mock import AsyncMock, MagicMock

    kb_helper = AsyncMock()
    kb_helper.list_documents = AsyncMock()
    kb_helper.count_documents = AsyncMock()

    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)

    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    service.knowledge_base_manager = kb_manager
    service.upload_progress = {}
    service.upload_tasks = {}
    return service, kb_helper


@pytest.mark.asyncio
async def test_list_documents_clamps_page_and_page_size_below_one():
    """page and page_size below 1 are clamped to 1 before calling kb_helper."""
    service, kb_helper = _make_service_with_mock_kb_helper()
    kb_helper.list_documents.return_value = []
    kb_helper.count_documents.return_value = 0

    await service.list_documents(kb_id="kb1", page=0, page_size=-5)

    kb_helper.list_documents.assert_awaited_once_with(offset=0, limit=1, search=None)


@pytest.mark.asyncio
async def test_list_documents_trims_search_and_turns_empty_to_none():
    """search is stripped; whitespace-only search becomes None."""
    service, kb_helper = _make_service_with_mock_kb_helper()
    kb_helper.list_documents.return_value = []
    kb_helper.count_documents.return_value = 0

    await service.list_documents(kb_id="kb1", page=1, page_size=10, search="   ")

    kb_helper.list_documents.assert_awaited_once_with(
        offset=0,
        limit=10,
        search=None,
    )


@pytest.mark.asyncio
async def test_list_documents_total_comes_from_count_documents():
    """total uses count_documents(search=normalized_search), not stale kb.doc_count."""
    service, kb_helper = _make_service_with_mock_kb_helper()
    kb_helper.list_documents.return_value = []
    kb_helper.count_documents.return_value = 42

    result = await service.list_documents(
        kb_id="kb1",
        page=1,
        page_size=10,
        search="  foo  ",
    )

    assert result["total"] == 42
    kb_helper.count_documents.assert_awaited_once_with(search="foo")


@pytest.mark.asyncio
async def test_list_documents_route_forwards_search_query(
    asgi_client: httpx.AsyncClient,
    knowledge_base_route_service: KnowledgeBaseService,
):
    knowledge_base_route_service.list_documents = AsyncMock(
        return_value={"items": [], "page": 2, "page_size": 5, "total": 0}
    )

    response = await asgi_client.get(
        "/api/v1/knowledge-bases/test_kb_id/documents?page=2&page_size=5&search=guide"
    )

    assert response.status_code == 200
    knowledge_base_route_service.list_documents.assert_awaited_once_with(
        kb_id="test_kb_id",
        page=2,
        page_size=5,
        search="guide",
    )


def test_get_upload_progress_reports_processing_completed_and_failed_states():
    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    service.upload_progress = {
        "task-processing": {"status": "processing", "current": 3, "total": 10},
    }
    service.upload_tasks = {
        "task-processing": {"status": "processing", "result": None, "error": None},
        "task-completed": {
            "status": "completed",
            "result": {"ok": True},
            "error": None,
        },
        "task-failed": {
            "status": "failed",
            "result": None,
            "error": "boom",
        },
    }

    assert service.get_upload_progress("task-processing") == {
        "task_id": "task-processing",
        "status": "processing",
        "progress": {"status": "processing", "current": 3, "total": 10},
    }
    assert service.get_upload_progress("task-completed") == {
        "task_id": "task-completed",
        "status": "completed",
        "result": {"ok": True},
    }
    assert service.get_upload_progress("task-failed") == {
        "task_id": "task-failed",
        "status": "failed",
        "error": "boom",
    }


def test_get_upload_progress_rejects_missing_or_unknown_task():
    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    service.upload_progress = {}
    service.upload_tasks = {}

    with pytest.raises(KnowledgeBaseServiceError, match="缺少参数 task_id"):
        service.get_upload_progress(None)

    with pytest.raises(KnowledgeBaseServiceError, match="找不到该任务"):
        service.get_upload_progress("missing")


@pytest.mark.asyncio
async def test_background_upload_from_url_task_marks_success_result():
    uploaded_doc = MagicMock()
    uploaded_doc.model_dump.return_value = {"doc_id": "doc-1"}
    kb_helper = AsyncMock()
    kb_helper.upload_from_url = AsyncMock(return_value=uploaded_doc)

    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    service.upload_progress = {}
    service.upload_tasks = {}

    await service.background_upload_from_url_task(
        task_id="task-url-ok",
        kb_helper=kb_helper,
        url="https://example.com/doc",
        chunk_size=512,
        chunk_overlap=50,
        batch_size=32,
        tasks_limit=3,
        max_retries=3,
        enable_cleaning=True,
        cleaning_provider_id="cleaner-1",
    )

    assert service.upload_tasks["task-url-ok"]["status"] == "completed"
    result = service.upload_tasks["task-url-ok"]["result"]
    assert result == {
        "task_id": "task-url-ok",
        "uploaded": [{"doc_id": "doc-1"}],
        "failed": [],
        "total": 1,
        "success_count": 1,
        "failed_count": 0,
    }
    kb_helper.upload_from_url.assert_awaited_once()


@pytest.mark.asyncio
async def test_background_upload_from_url_task_marks_failure_result():
    kb_helper = AsyncMock()
    kb_helper.upload_from_url = AsyncMock(side_effect=RuntimeError("fetch failed"))

    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    service.upload_progress = {}
    service.upload_tasks = {}

    await service.background_upload_from_url_task(
        task_id="task-url-fail",
        kb_helper=kb_helper,
        url="https://example.com/doc",
        chunk_size=512,
        chunk_overlap=50,
        batch_size=32,
        tasks_limit=3,
        max_retries=3,
        enable_cleaning=False,
        cleaning_provider_id=None,
    )

    assert service.upload_tasks["task-url-fail"]["status"] == "failed"
    assert (
        service.upload_tasks["task-url-fail"]["error"] == "Knowledge base task failed"
    )
    assert service.upload_progress["task-url-fail"]["status"] == "failed"


@pytest.mark.asyncio
async def test_list_kbs_clamps_page_and_includes_init_error():
    kb = MagicMock()
    kb.kb_id = "kb-1"
    kb.model_dump.return_value = {"kb_id": "kb-1", "kb_name": "One"}
    kb_helper = MagicMock(init_error="vector db failed")
    kb_manager = MagicMock()
    kb_manager.list_kbs = AsyncMock(return_value=[kb])
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)

    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    service.knowledge_base_manager = kb_manager
    service.upload_progress = {}
    service.upload_tasks = {}

    result = await service.list_kbs(page=0, page_size=0)

    assert result == {
        "items": [
            {
                "kb_id": "kb-1",
                "kb_name": "One",
                "init_error": "Knowledge base initialization failed",
            }
        ],
        "page": 1,
        "page_size": 1,
        "total": 1,
    }


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


@pytest.mark.asyncio
async def test_create_kb_wraps_embedding_validation_failure():
    provider = _EmbeddingProviderStub(vectors=[0.1], dim=2)
    kb_manager = MagicMock()
    kb_manager.provider_manager = MagicMock(
        get_provider_by_id=AsyncMock(return_value=provider)
    )

    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    service.knowledge_base_manager = kb_manager
    service.upload_progress = {}
    service.upload_tasks = {}

    with pytest.raises(KnowledgeBaseServiceError, match="测试嵌入模型失败"):
        await service.create_kb({"kb_name": "demo", "embedding_provider_id": "embed-1"})


@pytest.mark.asyncio
async def test_update_kb_uses_existing_name_when_name_is_omitted():
    kb_helper = MagicMock()
    kb_helper.kb = MagicMock()
    kb_helper.kb.kb_name = "Existing KB"
    kb_helper.kb.description = None
    kb_helper.kb.emoji = None
    kb_helper.kb.embedding_provider_id = None
    kb_helper.kb.rerank_provider_id = None
    kb_helper.kb.chunk_size = None
    kb_helper.kb.chunk_overlap = None
    kb_helper.kb.top_k_dense = None
    kb_helper.kb.top_k_sparse = None
    kb_helper.kb.top_m_final = None
    updated_helper = MagicMock()
    updated_helper.kb.model_dump.return_value = {
        "kb_id": "kb-1",
        "kb_name": "Existing KB",
    }
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    kb_manager.update_kb = AsyncMock(return_value=updated_helper)

    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    service.knowledge_base_manager = kb_manager
    service.upload_progress = {}
    service.upload_tasks = {}

    result, message = await service.update_kb(
        {"kb_id": "kb-1", "description": "updated description"}
    )

    assert result == {"kb_id": "kb-1", "kb_name": "Existing KB"}
    assert message == "更新知识库成功"
    kb_manager.update_kb.assert_awaited_once_with(
        kb_id="kb-1",
        kb_name="Existing KB",
        description="updated description",
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
async def test_update_kb_requires_at_least_one_field():
    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    service.knowledge_base_manager = MagicMock()
    service.upload_progress = {}
    service.upload_tasks = {}

    with pytest.raises(KnowledgeBaseServiceError, match="至少需要提供一个更新字段"):
        await service.update_kb({"kb_id": "kb-1"})


@pytest.mark.asyncio
async def test_delete_kb_raises_when_target_is_missing():
    kb_manager = MagicMock()
    kb_manager.delete_kb = AsyncMock(return_value=False)

    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    service.knowledge_base_manager = kb_manager
    service.upload_progress = {}
    service.upload_tasks = {}

    with pytest.raises(KnowledgeBaseServiceError, match="知识库不存在"):
        await service.delete_kb({"kb_id": "missing"})


@pytest.mark.asyncio
async def test_retrieve_reports_visualization_error_without_dropping_results(
    monkeypatch,
):
    kb_manager = MagicMock()
    kb_manager.retrieve = AsyncMock(
        return_value={"results": [{"doc_id": "doc-1", "score": 0.9}]}
    )

    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    service.knowledge_base_manager = kb_manager
    service.upload_progress = {}
    service.upload_tasks = {}

    async def fail_visualization(_query, _kb_names, _kb_manager):
        raise RuntimeError("tsne failed")

    monkeypatch.setattr(
        "astrbot.dashboard.services.knowledge_base_service.generate_tsne_visualization",
        fail_visualization,
    )

    result = await service.retrieve(
        {"query": "astrbot", "kb_names": ["kb-1"], "debug": True, "top_k": 2}
    )

    assert result == {
        "results": [{"doc_id": "doc-1", "score": 0.9}],
        "total": 1,
        "query": "astrbot",
        "visualization_error": "Visualization generation failed",
    }
    kb_manager.retrieve.assert_awaited_once_with(
        query="astrbot",
        kb_names=["kb-1"],
        top_m_final=2,
    )


@pytest.mark.asyncio
async def test_upload_document_sanitizes_filename_and_schedules_background_task(
    monkeypatch, tmp_path
):
    kb_helper = AsyncMock()
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)

    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    service.knowledge_base_manager = kb_manager
    service.upload_progress = {}
    service.upload_tasks = {}

    background_calls: list[dict] = []

    async def fake_background_upload_task(**kwargs):
        background_calls.append(kwargs)

    monkeypatch.setattr(
        service,
        "background_upload_task",
        fake_background_upload_task,
    )
    monkeypatch.setattr(
        "astrbot.dashboard.services.knowledge_base_service.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )

    response = await service.upload_document(
        content_type="multipart/form-data; boundary=test",
        form_data={
            "kb_id": "kb-1",
            "chunk_size": "256",
            "chunk_overlap": "32",
            "batch_size": "8",
            "tasks_limit": "2",
            "max_retries": "5",
        },
        files=[
            UploadFile(
                file=BytesIO(b"hello world"),
                filename="../unsafe name.txt",
            )
        ],
    )
    await asyncio.sleep(0)

    assert response["file_count"] == 1
    assert response["task_id"] in service.upload_tasks
    assert service.upload_tasks[response["task_id"]]["status"] == "pending"
    assert len(background_calls) == 1
    background_call = background_calls[0]
    assert background_call["task_id"] == response["task_id"]
    assert background_call["kb_helper"] is kb_helper
    assert background_call["chunk_size"] == 256
    assert background_call["chunk_overlap"] == 32
    assert background_call["batch_size"] == 8
    assert background_call["tasks_limit"] == 2
    assert background_call["max_retries"] == 5

    staging_dir = background_call["staging_dir"]
    assert staging_dir.parent == tmp_path
    assert staging_dir.name == f"kb_upload_{response['task_id']}"
    assert background_call["files_to_upload"] == [
        {
            "file_name": "unsafe name.txt",
            "temp_file_path": next(staging_dir.iterdir()),
            "file_type": "txt",
        }
    ]
    assert (
        background_call["files_to_upload"][0]["temp_file_path"].read_bytes()
        == b"hello world"
    )


@pytest.mark.asyncio
async def test_upload_route_collects_starlette_multipart_files(
    asgi_client: httpx.AsyncClient,
    knowledge_base_route_service: KnowledgeBaseService,
):
    knowledge_base_route_service.upload_document = AsyncMock(
        return_value={
            "task_id": "task-md",
            "file_count": 2,
            "message": "ok",
        }
    )

    response = await asgi_client.post(
        "/api/v1/knowledge-bases/test_kb_id/documents",
        data={"kb_id": "test_kb_id"},
        files=[
            ("file0", ("operators/阿米娅.md", "# 阿米娅\n".encode(), "text/markdown")),
            ("file1", ("items/源石.md", "# 源石\n".encode(), "text/markdown")),
        ],
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    uploaded = knowledge_base_route_service.upload_document.await_args.kwargs
    assert [file.filename for file in uploaded["files"]] == [
        "operators/阿米娅.md",
        "items/源石.md",
    ]


@pytest.mark.asyncio
async def test_upload_route_accepts_more_than_starlette_default_file_limit(
    asgi_client: httpx.AsyncClient,
    knowledge_base_route_service: KnowledgeBaseService,
):
    knowledge_base_route_service.upload_document = AsyncMock(
        return_value={
            "task_id": "task-1001",
            "file_count": 1001,
            "message": "ok",
        }
    )
    files = [
        (f"file{index}", (f"doc-{index}.md", b"# title\n", "text/markdown"))
        for index in range(1001)
    ]

    response = await asgi_client.post(
        "/api/v1/knowledge-bases/test_kb_id/documents",
        data={"kb_id": "test_kb_id"},
        files=files,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    uploaded = knowledge_base_route_service.upload_document.await_args.kwargs
    assert len(uploaded["files"]) == 1001


@pytest.mark.asyncio
async def test_get_document_raises_when_document_is_missing():
    kb_helper = AsyncMock()
    kb_helper.get_document = AsyncMock(return_value=None)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)

    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    service.knowledge_base_manager = kb_manager
    service.upload_progress = {}
    service.upload_tasks = {}

    with pytest.raises(KnowledgeBaseServiceError, match="文档不存在"):
        await service.get_document(kb_id="kb-1", doc_id="doc-404")


@pytest.mark.asyncio
async def test_delete_document_and_chunk_delegate_to_helper():
    kb_helper = AsyncMock()
    kb_helper.delete_document = AsyncMock()
    kb_helper.delete_chunk = AsyncMock()
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)

    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    service.knowledge_base_manager = kb_manager
    service.upload_progress = {}
    service.upload_tasks = {}

    delete_doc_result = await service.delete_document(
        {"kb_id": "kb-1", "doc_id": "doc-1"}
    )
    delete_chunk_result = await service.delete_chunk(
        {"kb_id": "kb-1", "chunk_id": "chunk-1", "doc_id": "doc-1"}
    )

    assert delete_doc_result == (None, "删除文档成功")
    assert delete_chunk_result == (None, "删除文本块成功")
    kb_helper.delete_document.assert_awaited_once_with("doc-1")
    kb_helper.delete_chunk.assert_awaited_once_with("chunk-1", "doc-1")


@pytest.mark.asyncio
async def test_list_chunks_returns_items_and_offset_page_metadata():
    kb_helper = AsyncMock()
    kb_helper.get_chunks_by_doc_id = AsyncMock(
        return_value=[{"chunk_id": "c-1"}, {"chunk_id": "c-2"}]
    )
    kb_helper.get_chunk_count_by_doc_id = AsyncMock(return_value=7)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)

    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    service.knowledge_base_manager = kb_manager
    service.upload_progress = {}
    service.upload_tasks = {}

    result = await service.list_chunks(
        kb_id="kb-1",
        doc_id="doc-1",
        page=3,
        page_size=2,
    )

    assert result == {
        "items": [{"chunk_id": "c-1"}, {"chunk_id": "c-2"}],
        "page": 3,
        "page_size": 2,
        "total": 7,
    }
    kb_helper.get_chunks_by_doc_id.assert_awaited_once_with(
        doc_id="doc-1",
        offset=4,
        limit=2,
    )
    kb_helper.get_chunk_count_by_doc_id.assert_awaited_once_with("doc-1")
