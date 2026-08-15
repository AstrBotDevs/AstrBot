import logging
import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.datastructures import UploadFile

from astrbot.dashboard.api import knowledge_bases as knowledge_bases_api
from astrbot.dashboard.api import providers as providers_api
from astrbot.dashboard.api import skills as skills_api
from astrbot.dashboard.responses import DashboardValidationError
from astrbot.dashboard.services.backup_service import BackupService
from astrbot.dashboard.services.config_service import ProviderConfigService
from astrbot.dashboard.services.file_service import FileService, FileServiceError
from astrbot.dashboard.services.knowledge_base_service import KnowledgeBaseService
from astrbot.dashboard.services.memory_service import MemoryService
from astrbot.dashboard.services.skills_service import SkillsService

_SENSITIVE_ERROR = (
    "api_key=api-key-top-secret "
    "Bearer bearer-secret-token "
    "password=dashboard-password "
    "https://internal.example/private/config "
    "C:\\private\\config\\secret.txt "
    "/srv/astrbot/private/config.json"
)
_SENSITIVE_VALUES = (
    "api-key-top-secret",
    "bearer-secret-token",
    "dashboard-password",
    "https://internal.example/private/config",
    "C:\\private\\config\\secret.txt",
    "/srv/astrbot/private/config.json",
)


def _assert_no_sensitive_values(*texts: str | None) -> None:
    for text in texts:
        assert text is not None
        for value in _SENSITIVE_VALUES:
            assert value not in text


def _backup_service() -> BackupService:
    service = BackupService.__new__(BackupService)
    service.db = MagicMock()
    service.knowledge_base_manager = None
    service.data_dir = "data"
    service.backup_dir = "backups"
    service.backup_tasks = {}
    service.backup_progress = {}
    return service


def _knowledge_base_service() -> KnowledgeBaseService:
    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    service.knowledge_base_manager = MagicMock()
    service.upload_progress = {}
    service.upload_tasks = {}
    service._background_tasks = set()
    return service


def _provider_config_service(target: object | None = None) -> ProviderConfigService:
    service = ProviderConfigService.__new__(ProviderConfigService)
    service.provider_manager = SimpleNamespace(
        inst_map={} if target is None else {"provider-id": target},
    )
    return service


@pytest.mark.asyncio
@pytest.mark.parametrize("task_type", ["export", "import"])
async def test_backup_background_task_errors_are_generic_and_logs_are_redacted(
    monkeypatch,
    caplog,
    task_type: str,
) -> None:
    service = _backup_service()
    task_id = f"backup-{task_type}"
    service._init_task(task_id, task_type)

    if task_type == "export":

        class FailingExporter:
            def __init__(self, **_kwargs) -> None:
                pass

            async def export_all(self, **_kwargs):
                raise RuntimeError(_SENSITIVE_ERROR)

        monkeypatch.setattr(
            "astrbot.dashboard.services.backup_service.AstrBotExporter",
            FailingExporter,
        )
        run_task = service.background_export_task(task_id)
    else:

        class FailingImporter:
            def __init__(self, **_kwargs) -> None:
                pass

            async def import_all(self, **_kwargs):
                raise RuntimeError(_SENSITIVE_ERROR)

        monkeypatch.setattr(
            "astrbot.dashboard.services.backup_service.AstrBotImporter",
            FailingImporter,
        )
        run_task = service.background_import_task(task_id, "backups/import.zip")

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        await run_task

    task = service.backup_tasks[task_id]
    assert task["status"] == "failed"
    assert task["error"] == "Backup task failed"
    _assert_no_sensitive_values(task["error"], caplog.text)


@pytest.mark.asyncio
async def test_backup_import_failure_result_and_log_are_redacted(
    monkeypatch,
    caplog,
) -> None:
    service = _backup_service()
    task_id = "backup-import-result"
    service._init_task(task_id, "import")

    class FailedImporter:
        def __init__(self, **_kwargs) -> None:
            pass

        async def import_all(self, **_kwargs):
            return SimpleNamespace(success=False, errors=[_SENSITIVE_ERROR])

    monkeypatch.setattr(
        "astrbot.dashboard.services.backup_service.AstrBotImporter",
        FailedImporter,
    )

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        await service.background_import_task(task_id, "backups/import.zip")

    task = service.backup_tasks[task_id]
    assert task["status"] == "failed"
    assert task["error"] == "Backup task failed"
    assert caplog.records
    _assert_no_sensitive_values(task["error"], caplog.text)


@pytest.mark.asyncio
async def test_provider_test_error_is_generic_through_service_and_api(caplog) -> None:
    target = SimpleNamespace(
        meta=lambda: SimpleNamespace(
            id="provider-id",
            model="test-model",
            provider_type=SimpleNamespace(value="text_to_speech"),
        ),
        test=AsyncMock(side_effect=RuntimeError(_SENSITIVE_ERROR)),
    )
    service = _provider_config_service(target)

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        service_result = await service.test_provider("provider-id")
        api_result = await providers_api.test_provider(
            provider_id="provider-id",
            _auth=object(),
            service=service,
        )

    assert service_result["status"] == "unavailable"
    assert service_result["error"] == "Provider test failed"
    assert api_result == {"status": "ok", "message": None, "data": service_result}
    _assert_no_sensitive_values(service_result["error"], str(api_result), caplog.text)


@pytest.mark.asyncio
async def test_provider_test_preserves_missing_provider_validation_error() -> None:
    service = _provider_config_service()

    with pytest.raises(DashboardValidationError, match="Provider missing not found"):
        await service.test_provider("missing")


@pytest.mark.asyncio
async def test_knowledge_base_document_failure_result_and_log_are_redacted(
    caplog,
    tmp_path,
) -> None:
    service = _knowledge_base_service()
    kb_helper = SimpleNamespace(
        upload_document=AsyncMock(side_effect=RuntimeError(_SENSITIVE_ERROR))
    )
    staging_dir = tmp_path / "kb-document"
    staging_dir.mkdir()
    temp_file_path = staging_dir / "document.txt"
    temp_file_path.write_bytes(b"content")

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        await service.background_upload_task(
            task_id="kb-document",
            kb_helper=kb_helper,
            files_to_upload=[
                {
                    "file_name": "document.txt",
                    "temp_file_path": temp_file_path,
                    "file_type": "txt",
                }
            ],
            staging_dir=staging_dir,
            chunk_size=256,
            chunk_overlap=32,
            batch_size=8,
            tasks_limit=1,
            max_retries=1,
        )

    result = service.upload_tasks["kb-document"]["result"]
    assert result["failed"] == [
        {"file_name": "document.txt", "error": "document.txt: Document upload failed"}
    ]
    _assert_no_sensitive_values(result["failed"][0]["error"], caplog.text)
    assert not staging_dir.exists()


@pytest.mark.asyncio
async def test_knowledge_base_url_background_failure_is_generic_and_redacted(
    caplog,
) -> None:
    service = _knowledge_base_service()
    kb_helper = SimpleNamespace(
        upload_from_url=AsyncMock(side_effect=RuntimeError(_SENSITIVE_ERROR))
    )

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        await service.background_upload_from_url_task(
            task_id="kb-url",
            kb_helper=kb_helper,
            url="https://example.invalid/article",
            chunk_size=256,
            chunk_overlap=32,
            batch_size=8,
            tasks_limit=1,
            max_retries=1,
            enable_cleaning=False,
            cleaning_provider_id=None,
        )

    task = service.upload_tasks["kb-url"]
    assert task["status"] == "failed"
    assert task["error"] == "Knowledge base task failed"
    _assert_no_sensitive_values(task["error"], caplog.text)


@pytest.mark.asyncio
async def test_knowledge_base_import_background_failure_is_generic_and_redacted(
    caplog,
) -> None:
    class FailingDocuments:
        def __len__(self) -> int:
            raise RuntimeError(_SENSITIVE_ERROR)

    service = _knowledge_base_service()

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        await service.background_import_task(
            task_id="kb-import",
            kb_helper=MagicMock(),
            documents=FailingDocuments(),
            batch_size=8,
            tasks_limit=1,
            max_retries=1,
        )

    task = service.upload_tasks["kb-import"]
    assert task["status"] == "failed"
    assert task["error"] == "Knowledge base task failed"
    _assert_no_sensitive_values(task["error"], caplog.text)


@pytest.mark.asyncio
async def test_memory_refresh_failure_state_and_log_are_redacted(caplog) -> None:
    service = MemoryService.__new__(MemoryService)
    service.refresh_tasks = {
        "memory-refresh": {
            "status": "pending",
            "result": None,
            "error": None,
            "updated_at": "",
        }
    }
    service.profile_refresher = SimpleNamespace(
        refresh=AsyncMock(side_effect=RuntimeError(_SENSITIVE_ERROR))
    )
    service.db = MagicMock()

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        await service._refresh_profile_task(  # noqa: SLF001
            "memory-refresh",
            person_id="person",
            chat_scope="isolated:webchat:FriendMessage:chat",
            operator="dashboard",
        )

    task = service.refresh_tasks["memory-refresh"]
    assert task["status"] == "failed"
    assert task["error"] == "Memory profile refresh failed"
    _assert_no_sensitive_values(task["error"], caplog.text)


@pytest.mark.asyncio
async def test_neo_operation_failure_is_generic_and_log_is_redacted(
    monkeypatch,
    caplog,
) -> None:
    class FailingBayClient:
        def __init__(self, **_kwargs) -> None:
            pass

        async def __aenter__(self):
            return object()

        async def __aexit__(self, _exc_type, _exc, _traceback) -> bool:
            return False

    service = SkillsService.__new__(SkillsService)
    monkeypatch.setattr(
        service,
        "get_neo_client_config",
        lambda: ("https://neo.example", "neo-access-token"),
    )
    monkeypatch.setitem(
        sys.modules,
        "shipyard_neo",
        SimpleNamespace(BayClient=FailingBayClient),
    )

    async def failing_operation(_client):
        raise RuntimeError(_SENSITIVE_ERROR)

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        result = await service.with_neo_client(failing_operation)

    assert result.ok is False
    assert result.message == "Neo operation failed"
    _assert_no_sensitive_values(result.message, caplog.text)


@pytest.mark.asyncio
async def test_neo_promotion_sync_error_is_generic_and_log_is_redacted(
    monkeypatch,
    caplog,
) -> None:
    class FailingSyncManager:
        def __init__(self, *, sync_active_sandboxes) -> None:
            self.sync_active_sandboxes = sync_active_sandboxes

        async def promote_with_optional_sync(self, _client, **_kwargs):
            return {
                "release": {"id": "release-1"},
                "sync": None,
                "rollback": {"id": "release-1"},
                "sync_error": _SENSITIVE_ERROR,
            }

    service = SkillsService.__new__(SkillsService)
    service.demo_mode = False
    service.computer_runtime = SimpleNamespace(
        sync_skills_to_active_sandboxes=AsyncMock()
    )

    async def run_neo_operation(operation):
        return await operation(object())

    monkeypatch.setattr(service, "with_neo_client", run_neo_operation)
    monkeypatch.setattr(
        "astrbot.dashboard.services.skills_service.NeoSkillSyncManager",
        FailingSyncManager,
    )

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        result = await service.promote_neo_candidate(
            {"candidate_id": "candidate-1", "stage": "stable"}
        )

    assert result.ok is False
    assert result.message == "Stable promotion failed and has been rolled back."
    _assert_no_sensitive_values(result.message, caplog.text)


@pytest.mark.asyncio
async def test_neo_configuration_validation_message_remains_specific() -> None:
    service = SkillsService.__new__(SkillsService)
    service.config = {"provider_settings": {"sandbox": {}}}

    result = await service.with_neo_client(lambda _client: None)

    assert result.ok is False
    assert result.message == (
        "Shipyard Neo endpoint or access token not configured. "
        "Set them in Dashboard or ensure Bay's credentials.json is accessible."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "message"),
    [
        (
            lambda service: service.resolve_local_skill_dir("invalid/skill"),
            "Invalid skill name",
        ),
        (
            lambda service: service.resolve_skill_relative_path(
                Path("unused"),
                "../secret.txt",
                expect_file=True,
            ),
            "Invalid relative path",
        ),
    ],
)
async def test_skills_path_validation_errors_remain_specific(
    operation, message
) -> None:
    """Safe user-input validation must not be turned into a 500 envelope."""
    service = SkillsService.__new__(SkillsService)

    response = await skills_api._run(lambda: operation(service))

    assert response == {"status": "error", "message": message}


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_kind", ["embedding", "rerank"])
async def test_knowledge_base_provider_failures_are_generic_and_redacted(
    caplog,
    provider_kind: str,
) -> None:
    """Provider exceptions must never become knowledge-base API messages."""

    class FailingEmbeddingProvider:
        async def get_embedding(self, _text: str):
            raise RuntimeError(_SENSITIVE_ERROR)

        def get_dim(self) -> int:
            return 1

    class FailingRerankProvider:
        async def rerank(self, **_kwargs):
            raise RuntimeError(_SENSITIVE_ERROR)

    from astrbot.core.provider.provider import EmbeddingProvider, RerankProvider

    class EmbeddingFailure(EmbeddingProvider):
        async def get_embedding(self, _text: str):
            return await FailingEmbeddingProvider().get_embedding(_text)

        async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
            _ = texts
            return []

        def get_dim(self) -> int:
            return FailingEmbeddingProvider().get_dim()

    class RerankFailure(RerankProvider):
        async def rerank(self, **kwargs):
            return await FailingRerankProvider().rerank(**kwargs)

    class EmbeddingSuccess(EmbeddingProvider):
        async def get_embedding(self, _text: str) -> list[float]:
            return [0.1]

        async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
            return [[0.1] for _ in texts]

        def get_dim(self) -> int:
            return 1

    providers = (
        [EmbeddingFailure({}, {})]
        if provider_kind == "embedding"
        else [
            EmbeddingSuccess({}, {}),
            RerankFailure({}, {}),
        ]
    )
    provider_manager = MagicMock(get_provider_by_id=AsyncMock(side_effect=providers))
    service = _knowledge_base_service()
    service.knowledge_base_manager.provider_manager = provider_manager
    payload = {"kb_name": "demo", "embedding_provider_id": "embedding"}
    if provider_kind == "rerank":
        payload["rerank_provider_id"] = "rerank"

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        response = await knowledge_bases_api._run(
            lambda: service.create_kb(payload),
            prefix="Knowledge base operation failed",
        )

    assert response == {
        "status": "error",
        "message": (
            "测试嵌入模型失败" if provider_kind == "embedding" else "测试重排序模型失败"
        ),
    }
    _assert_no_sensitive_values(response["message"], caplog.text)


@pytest.mark.asyncio
async def test_knowledge_base_initialization_state_is_generic_in_api_data() -> None:
    kb = MagicMock(kb_id="kb-1")
    kb.model_dump.return_value = {"kb_id": "kb-1", "kb_name": "Demo"}
    kb_manager = MagicMock(
        list_kbs=AsyncMock(return_value=[kb]),
        get_kb=AsyncMock(return_value=SimpleNamespace(init_error=_SENSITIVE_ERROR)),
    )
    service = _knowledge_base_service()
    service.knowledge_base_manager = kb_manager

    response = await knowledge_bases_api._run(
        lambda: service.list_kbs(page=1, page_size=20),
        prefix="Knowledge base operation failed",
    )

    assert response == {
        "status": "ok",
        "message": None,
        "data": {
            "items": [
                {
                    "kb_id": "kb-1",
                    "kb_name": "Demo",
                    "init_error": "Knowledge base initialization failed",
                }
            ],
            "page": 1,
            "page_size": 20,
            "total": 1,
        },
    }
    _assert_no_sensitive_values(str(response))


@pytest.mark.asyncio
async def test_batch_skill_upload_failure_is_generic_and_logs_are_redacted(
    monkeypatch,
    tmp_path: Path,
    caplog,
) -> None:
    service = SkillsService.__new__(SkillsService)
    service.demo_mode = False
    service.skill_manager = MagicMock()

    async def fail_upload(*_args, **_kwargs) -> None:
        raise RuntimeError(_SENSITIVE_ERROR)

    monkeypatch.setattr(
        "astrbot.dashboard.services.skills_service.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )
    monkeypatch.setattr(
        "astrbot.dashboard.services.skills_service.save_upload_to_path",
        fail_upload,
    )

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        result = await service.batch_upload_skills(
            [UploadFile(BytesIO(b"archive"), filename="demo.zip")]
        )

    assert result.data == {
        "total": 1,
        "succeeded": [],
        "failed": [{"filename": "demo.zip", "error": "Skill upload failed"}],
        "skipped": [],
    }
    _assert_no_sensitive_values(result.data["failed"][0]["error"], caplog.text)


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [FileNotFoundError, KeyError, OSError])
async def test_file_token_resolution_hides_internal_failures(error_type) -> None:
    service = FileService(
        SimpleNamespace(handle_file=AsyncMock(side_effect=error_type(_SENSITIVE_ERROR)))
    )

    with pytest.raises(FileServiceError) as exc_info:
        await service.resolve_token_file("file-token")

    assert str(exc_info.value) == "File not found"
    _assert_no_sensitive_values(str(exc_info.value))
