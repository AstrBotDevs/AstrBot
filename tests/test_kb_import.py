import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from astrbot.core import LogBroker
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.exceptions import KnowledgeBaseUploadError
from astrbot.core.knowledge_base.kb_helper import KBHelper
from astrbot.core.knowledge_base.models import KBDocument
from astrbot.core.utils.auth_password import (
    hash_dashboard_password,
    hash_md5_dashboard_password,
)
from astrbot.dashboard.asgi_runtime import FastAPIAppAdapter
from astrbot.dashboard.server import AstrBotDashboard
from astrbot.dashboard.services.knowledge_base_service import KnowledgeBaseService

_TEST_DASHBOARD_PASSWORD = "AstrbotTest123"


@pytest_asyncio.fixture(scope="module")
async def core_lifecycle_td(tmp_path_factory):
    """Creates and initializes a core lifecycle instance with a temporary database."""
    tmp_db_path = tmp_path_factory.mktemp("data") / "test_data_kb.db"
    db = SQLiteDatabase(str(tmp_db_path))
    log_broker = LogBroker()
    core_lifecycle = AstrBotCoreLifecycle(log_broker, db)
    await core_lifecycle.initialize()

    # Mock kb_manager and kb_helper
    kb_manager = MagicMock()
    kb_helper = AsyncMock(spec=KBHelper)

    # Configure get_kb to be an async mock that returns kb_helper
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)

    # Mock upload_document return value
    mock_doc = KBDocument(
        doc_id="test_doc_id",
        kb_id="test_kb_id",
        doc_name="test_file.txt",
        file_type="txt",
        file_size=100,
        file_path="",
        chunk_count=2,
        media_count=0,
    )
    kb_helper.upload_document.return_value = mock_doc

    # kb_manager.get_kb.return_value = kb_helper # Removed this line as it's handled above
    core_lifecycle.kb_manager = kb_manager
    generated_password = getattr(
        core_lifecycle.astrbot_config,
        "_generated_dashboard_password",
        None,
    )
    dashboard_password = generated_password or _TEST_DASHBOARD_PASSWORD
    if not generated_password:
        core_lifecycle.astrbot_config["dashboard"]["pbkdf2_password"] = (
            hash_dashboard_password(dashboard_password)
        )
        core_lifecycle.astrbot_config["dashboard"]["password"] = (
            hash_md5_dashboard_password(dashboard_password)
        )
    object.__setattr__(
        core_lifecycle,
        "_dashboard_plain_password",
        dashboard_password,
    )

    try:
        yield core_lifecycle
    finally:
        try:
            _stop_res = core_lifecycle.stop()
            if asyncio.iscoroutine(_stop_res):
                await _stop_res
        except Exception:
            pass


@pytest.fixture(scope="module")
def app(core_lifecycle_td: AstrBotCoreLifecycle):
    """Creates a FastAPIAppAdapter app instance for testing."""
    shutdown_event = asyncio.Event()
    server = AstrBotDashboard(core_lifecycle_td, core_lifecycle_td.db, shutdown_event)
    return server.app


def _resolve_dashboard_password(core_lifecycle_td: AstrBotCoreLifecycle) -> str:
    generated_password = getattr(core_lifecycle_td, "_dashboard_plain_password", None)
    if generated_password:
        return generated_password
    password = core_lifecycle_td.astrbot_config["dashboard"]["pbkdf2_password"]
    if isinstance(password, str) and password.startswith("pbkdf2_sha256$"):
        return "astrbot"
    return password


@pytest_asyncio.fixture(scope="module")
async def authenticated_header(
    app: FastAPIAppAdapter, core_lifecycle_td: AstrBotCoreLifecycle
):
    """Handles login and returns an authenticated header."""
    test_client = app.test_client()
    response = await test_client.post(
        "/api/auth/login",
        json={
            "username": core_lifecycle_td.astrbot_config["dashboard"]["username"],
            "password": _resolve_dashboard_password(core_lifecycle_td),
        },
    )
    data = await response.get_json()
    assert data["status"] == "ok"
    token = data["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_import_documents(
    app: FastAPIAppAdapter,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    """Tests the import documents functionality."""
    test_client = app.test_client()
    kb_helper = await core_lifecycle_td.kb_manager.get_kb("test_kb_id")
    kb_helper.upload_document.reset_mock()
    kb_helper.upload_document.side_effect = None

    # Test data
    import_data = {
        "kb_id": "test_kb_id",
        "documents": [
            {"file_name": "test_file_1.txt", "chunks": ["chunk1", "chunk2"]},
            {"file_name": "test_file_2.md", "chunks": ["chunk3", "chunk4", "chunk5"]},
        ],
    }

    # Send request
    response = await test_client.post(
        "/api/kb/document/import", json=import_data, headers=authenticated_header
    )

    # Verify response
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert "task_id" in data["data"]
    assert data["data"]["doc_count"] == 2

    task_id = data["data"]["task_id"]

    # Wait for background task to complete (mocked)
    # Since we mocked upload_document, it should be fast, but we might need to poll progress
    for _ in range(10):
        progress_response = await test_client.get(
            f"/api/kb/document/upload/progress?task_id={task_id}",
            headers=authenticated_header,
        )
        progress_data = await progress_response.get_json()
        if progress_data["data"]["status"] == "completed":
            break
        await asyncio.sleep(0.1)

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
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    kb_helper = await core_lifecycle_td.kb_manager.get_kb("test_kb_id")
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
    app: FastAPIAppAdapter, authenticated_header: dict
):
    """Tests import documents with invalid input."""
    test_client = app.test_client()

    # Missing kb_id
    response = await test_client.post(
        "/api/kb/document/import", json={"documents": []}, headers=authenticated_header
    )
    data = await response.get_json()
    assert data["status"] == "error"
    assert "缺少参数 kb_id" in data["message"]

    # Missing documents
    response = await test_client.post(
        "/api/kb/document/import",
        json={"kb_id": "test_kb"},
        headers=authenticated_header,
    )
    data = await response.get_json()
    assert data["status"] == "error"
    assert "缺少参数 documents" in data["message"]

    # Invalid document format
    response = await test_client.post(
        "/api/kb/document/import",
        json={
            "kb_id": "test_kb",
            "documents": [{"file_name": "test"}],  # Missing chunks
        },
        headers=authenticated_header,
    )
    data = await response.get_json()
    assert data["status"] == "error"
    assert "文档格式错误" in data["message"]

    # Invalid chunks type
    response = await test_client.post(
        "/api/kb/document/import",
        json={
            "kb_id": "test_kb",
            "documents": [{"file_name": "test", "chunks": "not-a-list"}],
        },
        headers=authenticated_header,
    )
    data = await response.get_json()
    assert data["status"] == "error"
    assert "chunks 必须是列表" in data["message"]

    # Invalid chunks content
    response = await test_client.post(
        "/api/kb/document/import",
        json={
            "kb_id": "test_kb",
            "documents": [{"file_name": "test", "chunks": ["valid", ""]}],
        },
        headers=authenticated_header,
    )
    data = await response.get_json()
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
    service.core_lifecycle = MagicMock()
    service.core_lifecycle.kb_manager = kb_manager
    service.upload_progress = {}
    service.upload_tasks = {}
    return service, kb_helper


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unsafe_name",
    ["../../../outside.csv", "..\\..\\..\\outside.csv"],
)
async def test_table_upload_sanitizes_multipart_filename(
    unsafe_name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    outside_file = tmp_path / "outside.csv"
    outside_file.write_bytes(b"keep me")

    class UploadedFile:
        filename = unsafe_name
        saved_path: Path | None = None

        async def save(self, path) -> None:
            self.saved_path = Path(path)
            self.saved_path.write_bytes(b"table content")

    monkeypatch.setattr(
        "astrbot.dashboard.services.knowledge_base_service.get_astrbot_temp_path",
        lambda: str(temp_dir),
    )
    uploaded_file = UploadedFile()

    file_name, file_content = (
        await KnowledgeBaseService._save_and_read_upload_file(uploaded_file)
    )

    assert file_name == "outside.csv"
    assert file_content == b"table content"
    assert uploaded_file.saved_path is not None
    assert uploaded_file.saved_path.parent == temp_dir
    assert not uploaded_file.saved_path.exists()
    assert outside_file.read_bytes() == b"keep me"


@pytest.mark.asyncio
async def test_table_upload_uses_fallback_for_empty_filename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()

    class UploadedFile:
        filename = None

        async def save(self, path) -> None:
            Path(path).write_bytes(b"table content")

    monkeypatch.setattr(
        "astrbot.dashboard.services.knowledge_base_service.get_astrbot_temp_path",
        lambda: str(temp_dir),
    )

    file_name, file_content = await KnowledgeBaseService._save_and_read_upload_file(
        UploadedFile(),
    )

    assert file_name == "document"
    assert file_content == b"table content"


@pytest.mark.asyncio
async def test_table_import_persists_index_text_separately_from_returned_content():
    helper = KBHelper.__new__(KBHelper)
    helper.kb = SimpleNamespace(kb_id="kb-1")
    helper._ensure_vec_db = AsyncMock()
    insert_error = KnowledgeBaseUploadError(
        stage="storage",
        user_message="stop after capturing insert payload",
    )
    helper.vec_db = SimpleNamespace(
        insert_batch=AsyncMock(side_effect=insert_error),
    )

    with pytest.raises(KnowledgeBaseUploadError) as exc_info:
        await helper.upload_table_document(
            file_name="products.csv",
            file_type="csv",
            headers=["sku", "description"],
            rows=[["apple-123", "red widget"]],
            columns_config=[
                {"name": "sku", "is_index": True, "is_returned": False},
                {
                    "name": "description",
                    "is_index": False,
                    "is_returned": True,
                },
            ],
        )

    assert exc_info.value is insert_error
    insert_kwargs = helper.vec_db.insert_batch.await_args.kwargs
    assert insert_kwargs["contents"] == ["description: red widget"]
    assert insert_kwargs["embedding_texts"] == ["sku: apple-123"]
    assert insert_kwargs["metadatas"][0]["index_text"] == "sku: apple-123"
    assert "apple-123" not in insert_kwargs["contents"][0]


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
        offset=0, limit=10, search=None,
    )


@pytest.mark.asyncio
async def test_list_documents_total_comes_from_count_documents():
    """total uses count_documents(search=normalized_search), not stale kb.doc_count."""
    service, kb_helper = _make_service_with_mock_kb_helper()
    kb_helper.list_documents.return_value = []
    kb_helper.count_documents.return_value = 42

    result = await service.list_documents(
        kb_id="kb1", page=1, page_size=10, search="  foo  ",
    )

    assert result["total"] == 42
    kb_helper.count_documents.assert_awaited_once_with(search="foo")
