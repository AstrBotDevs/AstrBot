import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from quart import Quart

from astrbot.core import LogBroker
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.exceptions import KnowledgeBaseUploadError
from astrbot.core.knowledge_base.kb_helper import KBHelper
from astrbot.core.knowledge_base.models import KBDocument
from astrbot.core.utils.auth_password import (
    hash_dashboard_password,
    hash_legacy_dashboard_password,
)
from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute
from astrbot.dashboard.server import AstrBotDashboard

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
            hash_legacy_dashboard_password(dashboard_password)
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
    """Creates a Quart app instance for testing."""
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
async def authenticated_header(app: Quart, core_lifecycle_td: AstrBotCoreLifecycle):
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
    app: Quart, authenticated_header: dict, core_lifecycle_td: AstrBotCoreLifecycle
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

    route = KnowledgeBaseRoute.__new__(KnowledgeBaseRoute)
    route.upload_progress = {}
    route.upload_tasks = {}

    await KnowledgeBaseRoute._background_import_task(
        route,
        task_id="task-1",
        kb_helper=kb_helper,
        documents=[{"file_name": "broken.txt", "chunks": ["chunk1", "chunk2"]}],
        batch_size=32,
        tasks_limit=3,
        max_retries=3,
    )

    assert route.upload_tasks["task-1"]["status"] == "completed"
    result = route.upload_tasks["task-1"]["result"]
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
async def test_import_documents_invalid_input(app: Quart, authenticated_header: dict):
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
