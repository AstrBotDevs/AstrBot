"""Exercise shared dashboard operations through real adapters and files."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import zipfile
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
import pytest_asyncio
from quart import Quart

from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.config.default import VERSION
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle, LifecycleState
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.log import LogBroker
from astrbot.core.platform import Platform
from astrbot.core.platform.manager import PlatformManager
from astrbot.core.platform.platform import PlatformStatus
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.lark.app_registration import LarkAppRegistration
from astrbot.core.platform.sources.lark.bot_info import LarkBotInfo
from astrbot.dashboard.routes import platform as platform_route_module
from astrbot.dashboard.routes.backup import BackupRoute
from astrbot.dashboard.routes.platform import PlatformRoute
from astrbot.dashboard.routes.route import RouteContext
from astrbot.dashboard.services import platform_service as platform_service_module
from astrbot.dashboard.services.backup_service import BackupService, BackupServiceError
from astrbot.dashboard.services.platform_service import (
    PlatformService,
    PlatformServiceError,
)


@dataclass
class BackupBoundary:
    app: Quart
    route: BackupRoute
    service: BackupService
    backup_dir: Path
    token: str


@pytest_asyncio.fixture
async def backup_boundary(
    database: SQLiteDatabase, astrbot_config: AstrBotConfig, tmp_path: Path
) -> AsyncIterator[BackupBoundary]:
    core = AstrBotCoreLifecycle(LogBroker(), database)
    core.astrbot_config = astrbot_config
    astrbot_config["dashboard"]["jwt_secret"] = "isolated-backup-test-secret"
    app = Quart(__name__)
    route = BackupRoute(RouteContext(astrbot_config, app), database, core)
    service = BackupService(database, core)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for state in (route, service):
        state.backup_dir = str(backup_dir)
        state.chunks_dir = str(backup_dir / ".chunks")
    service.chunked_uploads.chunks_root = backup_dir / ".chunks"
    token = jwt.encode(
        {"exp": datetime.now(UTC) + timedelta(minutes=5)},
        astrbot_config["dashboard"]["jwt_secret"],
        algorithm="HS256",
    )
    try:
        yield BackupBoundary(app, route, service, backup_dir, token)
    finally:
        tasks = (route._cleanup_task, service.chunked_uploads._cleanup_task)
        for task in tasks:
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task


def write_archive(path: Path, manifest: dict | None) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("payload.txt", "retained payload")
        if manifest is not None:
            archive.writestr("manifest.json", json.dumps(manifest))


@pytest.mark.parametrize("kind", ["valid", "missing", "bad-json", "bad-zip"])
def test_manifest_readers_preserve_archives(
    backup_boundary: BackupBoundary, kind: str
) -> None:
    path = backup_boundary.backup_dir / "archive.zip"
    manifest = {"astrbot_version": VERSION, "origin": "uploaded", "custom": [1, 2]}
    if kind == "bad-zip":
        path.write_bytes(b"not a zip archive")
    elif kind == "bad-json":
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("manifest.json", "{invalid")
    else:
        write_archive(path, manifest if kind == "valid" else None)
    before = path.read_bytes()

    expected = manifest if kind == "valid" else None
    assert backup_boundary.route._get_backup_manifest(str(path)) == expected
    assert backup_boundary.service.get_backup_manifest(str(path)) == expected
    assert path.read_bytes() == before


async def test_backup_list_keeps_filtering_defaults_order_and_pagination(
    backup_boundary: BackupBoundary,
) -> None:
    root = backup_boundary.backup_dir
    write_archive(root / "older.zip", {})
    write_archive(
        root / "newer.zip",
        {"origin": "uploaded", "astrbot_version": VERSION, "exported_at": "saved"},
    )
    write_archive(root / ".hidden.zip", {})
    write_archive(root / "missing-manifest.zip", None)
    (root / "broken.zip").write_text("broken")
    (root / "directory.zip").mkdir()
    (root / "notes.txt").write_text("ignore")
    os.utime(root / "older.zip", (1000, 1000))
    os.utime(root / "newer.zip", (2000, 2000))

    response = await backup_boundary.app.test_client().get(
        "/api/backup/list?page=2&page_size=1"
    )
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {
        "status": "ok",
        "message": None,
        "data": backup_boundary.service.list_backups(page=2, page_size=1),
    }
    assert body["data"] == {
        "items": [
            {
                "filename": "older.zip",
                "size": (root / "older.zip").stat().st_size,
                "created_at": 1000,
                "type": "exported",
                "astrbot_version": "未知",
                "exported_at": None,
            }
        ],
        "total": 2,
        "page": 2,
        "page_size": 1,
    }


@pytest.mark.parametrize("implementation", ["route", "service"])
def test_upload_marker_preserves_manifest_and_archive_payload(
    backup_boundary: BackupBoundary, implementation: str
) -> None:
    path = backup_boundary.backup_dir / "uploaded.zip"
    write_archive(path, {"astrbot_version": VERSION, "custom": {"keep": True}})
    with pytest.warns(UserWarning, match="Duplicate name"):
        if implementation == "route":
            backup_boundary.route._mark_backup_as_uploaded(str(path))
        else:
            backup_boundary.service.mark_backup_as_uploaded(str(path))
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert archive.read("payload.txt") == b"retained payload"
    assert manifest["origin"] == "uploaded"
    assert manifest["astrbot_version"] == VERSION
    assert manifest["custom"] == {"keep": True}
    assert datetime.fromisoformat(manifest["uploaded_at"]).tzinfo is None


@pytest.mark.parametrize("operation", ["check", "import", "delete", "download"])
@pytest.mark.parametrize(
    "filename", ["../outside.zip", "/outside.zip", r"dir\outside.zip", "a..zip"]
)
async def test_backup_routes_reject_paths_without_touching_files(
    backup_boundary: BackupBoundary, operation: str, filename: str
) -> None:
    outside = backup_boundary.backup_dir.parent / "outside.zip"
    outside.write_bytes(b"outside remains")
    inside = backup_boundary.backup_dir / "inside.zip"
    inside.write_bytes(b"inside remains")
    client = backup_boundary.app.test_client()
    if operation == "download":
        response = await client.get(
            "/api/backup/download",
            query_string={"filename": filename, "token": backup_boundary.token},
        )
    else:
        response = await client.post(
            f"/api/backup/{operation}",
            json={"filename": filename, "confirmed": True},
        )
    assert response.status_code == 200
    assert await response.get_json() == {
        "status": "error",
        "message": "无效的文件名",
        "data": {},
    }
    with pytest.raises(BackupServiceError, match="无效的文件名"):
        backup_boundary.service.delete_backup({"filename": filename})
    assert outside.read_bytes() == b"outside remains"
    assert inside.read_bytes() == b"inside remains"
    assert not backup_boundary.route.tasks


@pytest.mark.parametrize("operation", ["check", "import", "delete", "download"])
async def test_backup_missing_files_keep_endpoint_specific_errors(
    backup_boundary: BackupBoundary, operation: str
) -> None:
    client = backup_boundary.app.test_client()
    if operation == "download":
        response = await client.get(
            "/api/backup/download",
            query_string={"filename": "missing.zip", "token": backup_boundary.token},
        )
    else:
        response = await client.post(
            f"/api/backup/{operation}",
            json={"filename": "missing.zip", "confirmed": True},
        )
    expected = "备份文件不存在"
    if operation in {"check", "import"}:
        expected += ": missing.zip"
    assert await response.get_json() == {
        "status": "error",
        "message": expected,
        "data": {},
    }
    assert not backup_boundary.route.tasks


async def test_backup_real_precheck_range_download_and_delete(
    backup_boundary: BackupBoundary,
) -> None:
    path = backup_boundary.backup_dir / "archive.zip"
    write_archive(path, {"astrbot_version": VERSION, "exported_at": "saved"})
    original = path.read_bytes()
    client = backup_boundary.app.test_client()
    checked = await client.post("/api/backup/check", json={"filename": path.name})
    payload = await checked.get_json()
    assert payload["status"] == "ok"
    assert payload["data"] == backup_boundary.service.check_backup(
        {"filename": path.name}
    )
    assert payload["data"]["valid"] is True
    assert payload["data"]["can_import"] is True
    downloaded = await client.get(
        "/api/backup/download",
        query_string={"filename": path.name, "token": backup_boundary.token},
        headers={"Range": "bytes=0-3"},
    )
    assert downloaded.status_code == 206
    assert await downloaded.get_data() == original[:4]
    assert downloaded.headers["Content-Range"] == f"bytes 0-3/{len(original)}"
    assert path.read_bytes() == original
    deleted = await client.post("/api/backup/delete", json={"filename": path.name})
    assert await deleted.get_json() == {
        "status": "ok",
        "message": "删除备份成功",
        "data": {},
    }
    assert not path.exists()


async def test_legacy_import_still_requires_confirmation_before_path_resolution(
    backup_boundary: BackupBoundary,
) -> None:
    response = await backup_boundary.app.test_client().post(
        "/api/backup/import", json={"filename": "../outside.zip", "confirmed": False}
    )
    assert await response.get_json() == {
        "status": "error",
        "message": "请先确认导入｡导入将会清空并覆盖现有数据,此操作不可撤销｡",
        "data": {},
    }
    assert not backup_boundary.route.tasks
    assert backup_boundary.route.backup_tasks == {}


@pytest.mark.parametrize("status", ["pending", "processing", "completed", "failed"])
async def test_backup_progress_retains_callback_updates_and_result_shapes(
    backup_boundary: BackupBoundary, status: str
) -> None:
    for state in (backup_boundary.route, backup_boundary.service):
        state._init_task("job", "export")
        if status != "pending":
            state._set_task_result("job", "processing")
            await state._make_progress_callback("job")("compressing", 5, 10, "half")
            if status == "completed":
                state._set_task_result("job", status, result={"filename": "done.zip"})
            elif status == "failed":
                state._set_task_result("job", status, error="disk full")
    response = await backup_boundary.app.test_client().get(
        "/api/backup/progress?task_id=job"
    )
    payload = await response.get_json()
    assert payload["data"] == backup_boundary.service.get_progress("job")
    assert payload["data"]["type"] == "export"
    assert payload["data"]["status"] == status
    if status == "processing":
        assert payload["data"]["progress"] == {
            "status": "processing",
            "stage": "compressing",
            "current": 5,
            "total": 10,
            "message": "half",
        }
    elif status == "completed":
        assert payload["data"]["result"] == {"filename": "done.zip"}
    elif status == "failed":
        assert payload["data"]["error"] == "disk full"
    else:
        assert set(payload["data"]) == {"task_id", "type", "status"}


class RecordingPlatform(Platform):
    def __init__(self, config: dict, queue: asyncio.Queue) -> None:
        super().__init__(config, queue)
        self.requests: list[object] = []

    async def run(self) -> None:
        raise AssertionError("A webhook lookup must not start an adapter")

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata("test", "Isolated webhook boundary", self.config["id"])

    async def webhook_callback(self, request_obj: object) -> dict[str, str]:
        self.requests.append(request_obj)
        return {"adapter": self.config["id"]}


@dataclass
class PlatformBoundary:
    app: Quart
    route: PlatformRoute
    service: PlatformService
    core: AstrBotCoreLifecycle


@pytest.fixture
def platform_boundary(
    database: SQLiteDatabase, astrbot_config: AstrBotConfig
) -> PlatformBoundary:
    core = AstrBotCoreLifecycle(LogBroker(), database)
    core.astrbot_config = astrbot_config
    core.platform_manager = PlatformManager(astrbot_config, asyncio.Queue())
    app = Quart(__name__)
    route = PlatformRoute(RouteContext(astrbot_config, app), core)
    return PlatformBoundary(app, route, PlatformService(core), core)


async def test_webhook_lookup_uses_first_enabled_match_without_lifecycle_changes(
    platform_boundary: PlatformBoundary,
) -> None:
    manager = platform_boundary.core.platform_manager
    adapters = [
        RecordingPlatform(
            {"id": name, "webhook_uuid": webhook, "unified_webhook_mode": enabled},
            manager.event_queue,
        )
        for name, webhook, enabled in [
            ("disabled", "wanted", False),
            ("different", "other", True),
            ("first", "wanted", True),
            ("second", "wanted", True),
        ]
    ]
    manager.platform_insts.extend(adapters)
    assert platform_boundary.route._find_platform_by_uuid("wanted") is adapters[2]
    assert platform_boundary.service.find_platform_by_uuid("wanted") is adapters[2]
    sentinel = object()
    assert await platform_boundary.service.handle_webhook_callback(
        "wanted", sentinel
    ) == {"adapter": "first"}
    response = await platform_boundary.app.test_client().get(
        "/api/platform/webhook/wanted"
    )
    assert await response.get_json() == {"adapter": "first"}
    assert adapters[2].requests[0] is sentinel
    assert [len(adapter.requests) for adapter in adapters] == [0, 0, 2, 0]
    assert all(adapter.status is PlatformStatus.PENDING for adapter in adapters)
    assert manager._platform_tasks == {}
    assert platform_boundary.core.lifecycle_state is LifecycleState.CREATED
    assert manager.platform_insts == adapters


async def test_missing_webhook_preserves_status_and_route_without_manager(
    platform_boundary: PlatformBoundary,
) -> None:
    response = await platform_boundary.app.test_client().get(
        "/api/platform/webhook/missing"
    )
    assert response.status_code == 404
    assert await response.get_json() == {
        "status": "error",
        "message": "未找到对应平台",
        "data": {},
    }
    with pytest.raises(PlatformServiceError, match="未找到对应平台") as caught:
        await platform_boundary.service.handle_webhook_callback("missing", object())
    assert caught.value.status_code == 404
    platform_boundary.route.platform_manager = None
    assert platform_boundary.route._find_platform_by_uuid("missing") is None


@pytest.mark.parametrize("platform_config", [None, "invalid", [], {"domain": " lark "}])
async def test_lark_registration_normalizes_request_and_preserves_response(
    platform_boundary: PlatformBoundary,
    monkeypatch: pytest.MonkeyPatch,
    platform_config: object,
) -> None:
    domains: list[str] = []

    async def request_registration(domain: str) -> LarkAppRegistration:
        domains.append(domain)
        return LarkAppRegistration("device", "user", "verify", "verify-all", 120, 3)

    for module in (platform_route_module, platform_service_module):
        monkeypatch.setattr(module, "request_app_registration", request_registration)
    payload = {"action": " START ", "platform_config": platform_config}
    result = await platform_boundary.service.handle_platform_registration(
        "lark", payload
    )
    response = await platform_boundary.app.test_client().post(
        "/api/platform/registration/lark", json=payload
    )
    assert response.status_code == 200
    assert await response.get_json() == {
        "status": "ok",
        "message": None,
        "data": result,
    }
    assert result == {
        "status": "pending",
        "device_code": "device",
        "registration_code": "device",
        "user_code": "user",
        "verification_uri": "verify",
        "verification_uri_complete": "verify-all",
        "expires_in": 120,
        "interval": 3,
    }
    assert domains == (
        ["lark", "lark"] if isinstance(platform_config, dict) else ["", ""]
    )


@pytest.mark.parametrize("status", ["created", "pending"])
@pytest.mark.parametrize("metadata_fails", [False, True])
async def test_lark_poll_enriches_only_created_results_and_tolerates_metadata_failure(
    platform_boundary: PlatformBoundary,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    metadata_fails: bool,
) -> None:
    calls: list[dict[str, str]] = []
    original = {
        "status": status,
        "domain": "result-domain",
        "app_id": "app",
        "app_secret": "secret",
    }

    async def poll_registration(*, domain: str, device_code: str) -> dict:
        assert domain == "request-domain"
        assert device_code == "device"
        return dict(original)

    async def request_bot_info(
        *, domain: str, app_id: str, app_secret: str
    ) -> LarkBotInfo:
        calls.append({"domain": domain, "app_id": app_id, "app_secret": app_secret})
        if metadata_fails:
            raise RuntimeError("metadata unavailable")
        return LarkBotInfo("Visible bot", "bot-open-id")

    for module in (platform_route_module, platform_service_module):
        monkeypatch.setattr(module, "poll_app_registration_once", poll_registration)
        monkeypatch.setattr(module, "request_lark_bot_info", request_bot_info)
    payload = {
        "action": "poll",
        "registration_code": " device ",
        "platform_config": {"domain": " request-domain "},
    }
    result = await platform_boundary.service.handle_platform_registration(
        "lark", payload
    )
    response = await platform_boundary.app.test_client().post(
        "/api/platform/registration/lark", json=payload
    )
    assert response.status_code == 200
    assert await response.get_json() == {
        "status": "ok",
        "message": None,
        "data": result,
    }
    expected = dict(original)
    if status == "created" and not metadata_fails:
        expected.update(bot_name="Visible bot", bot_open_id="bot-open-id")
    assert result == expected
    assert "bot_name" not in original
    assert calls == (
        [{"domain": "result-domain", "app_id": "app", "app_secret": "secret"}] * 2
        if status == "created"
        else []
    )


@pytest.mark.parametrize(
    ("platform_type", "payload", "message", "status_code"),
    [
        ("lark", {}, "Missing action", 400),
        (
            "unknown",
            {"action": "start"},
            "Unsupported platform registration: unknown",
            404,
        ),
        ("lark", {"action": "stop"}, "Unsupported action: stop", 400),
        ("lark", {"action": "poll"}, "Missing device_code", 400),
        ("dingtalk", {"action": "poll"}, "Missing device_code", 400),
        ("weixin_oc", {"action": "poll"}, "Missing qrcode", 400),
    ],
)
async def test_registration_errors_keep_messages_and_http_status(
    platform_boundary: PlatformBoundary,
    platform_type: str,
    payload: dict,
    message: str,
    status_code: int,
) -> None:
    with pytest.raises(PlatformServiceError) as caught:
        await platform_boundary.service.handle_platform_registration(
            platform_type, payload
        )
    assert str(caught.value) == message
    assert caught.value.status_code == status_code
    response = await platform_boundary.app.test_client().post(
        f"/api/platform/registration/{platform_type}", json=payload
    )
    assert response.status_code == status_code
    assert await response.get_json() == {
        "status": "error",
        "message": message,
        "data": None,
    }
