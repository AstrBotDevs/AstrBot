"""Unit and API integration tests for configurable backup export directory."""

from __future__ import annotations

import asyncio
import json
import os
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import jwt
import pytest
from fastapi import FastAPI

from astrbot.core.config.default import CONFIG_METADATA_2, DEFAULT_CONFIG, VERSION
from astrbot.core.utils.astrbot_path import (
    ASTRBOT_BACKUP_DIR_ENV,
    get_astrbot_backups_path,
    get_default_astrbot_backups_path,
    validate_astrbot_backup_dir,
)
from astrbot.dashboard.api.backups import legacy_router as legacy_backups_router
from astrbot.dashboard.api.backups import router as backups_router
from astrbot.dashboard.services.backup_service import (
    BackupService,
    BackupServiceError,
)
from astrbot.dashboard.services.config_service import validate_config

JWT_SECRET = "test-backup-dir-jwt-secret-1234567890"


class _FakeConfig(dict):
    """Minimal AstrBotConfig-compatible dict that persists to JSON."""

    def __init__(self, path: Path, initial: dict | None = None) -> None:
        super().__init__(initial or {})
        self._path = path
        self.save_calls = 0

    def save_config(self) -> None:
        self.save_calls += 1
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(dict(self), indent=2), encoding="utf-8")


class _StubUploadFile:
    def __init__(self, filename: str, data: bytes) -> None:
        self.filename = filename
        self._data = data

    async def save(self, destination, *, max_bytes=None) -> int:
        Path(destination).write_bytes(self._data)
        return len(self._data)


def _create_valid_backup_zip(
    path: Path, *, origin: str = "exported", version: str = VERSION
) -> Path:
    manifest = {
        "version": "1.1",
        "astrbot_version": version,
        "exported_at": "2026-11-22T03:30:00+00:00",
        "origin": origin,
        "tables": {"main_db": [], "kb_metadata": [], "kb_documents": {}},
        "files": {"attachments": [], "kb_media": {}},
        "directories": [],
        "checksums": {},
        "statistics": {"main_db": {}, "kb_metadata": {}, "directories": {}},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("databases/main_db.json", json.dumps({}))
    return path


def _make_mock_db() -> MagicMock:
    db = MagicMock()
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=result)
    db.get_db.return_value = AsyncMock(
        __aenter__=AsyncMock(return_value=session),
        __aexit__=AsyncMock(return_value=None),
    )
    return db


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "astrbot_root"
    data = root / "data"
    data.mkdir(parents=True)
    monkeypatch.setenv("ASTRBOT_ROOT", str(root))
    monkeypatch.delenv(ASTRBOT_BACKUP_DIR_ENV, raising=False)
    config = _FakeConfig(
        data / "cmd_config.json",
        {
            "backup_dir": "",
            "dashboard": {"jwt_secret": JWT_SECRET},
        },
    )
    config.save_config()
    lifecycle = SimpleNamespace(astrbot_config=config, kb_manager=None)
    service = BackupService(db=_make_mock_db(), core_lifecycle=lifecycle)
    return SimpleNamespace(
        tmp_path=tmp_path,
        root=root,
        data=data,
        config=config,
        service=service,
    )


class TestBackupPathResolutionAndValidation:
    def test_default_path_backward_compatibility(self, isolated_env):
        expected = os.path.realpath(str(isolated_env.data / "backups"))
        assert get_default_astrbot_backups_path() == expected
        assert get_astrbot_backups_path() == expected
        assert get_astrbot_backups_path("") == expected
        assert get_astrbot_backups_path("   ") == expected

    def test_relative_and_absolute_resolution(self, isolated_env):
        rel = get_astrbot_backups_path("my_backups")
        assert rel == os.path.realpath(str(isolated_env.data / "my_backups"))

        external = isolated_env.tmp_path / "external_exports"
        assert get_astrbot_backups_path(str(external)) == os.path.realpath(
            str(external)
        )

    def test_env_var_precedence(self, isolated_env, monkeypatch: pytest.MonkeyPatch):
        env_target = isolated_env.tmp_path / "env_exports"
        monkeypatch.setenv(ASTRBOT_BACKUP_DIR_ENV, str(env_target))
        assert get_astrbot_backups_path(
            str(isolated_env.tmp_path / "ignored_dir")
        ) == os.path.realpath(str(env_target))

    def test_rejects_filesystem_root(self, isolated_env):
        root_anchor = Path(isolated_env.tmp_path).anchor
        with pytest.raises(ValueError, match="filesystem root"):
            validate_astrbot_backup_dir(root_anchor)

    def test_rejects_bare_home_directory(self, isolated_env):
        with pytest.raises(ValueError, match="home directory|parent directories"):
            validate_astrbot_backup_dir("~")

    def test_rejects_astrbot_root_data_and_ancestors(self, isolated_env):
        for forbidden in (
            isolated_env.root,
            isolated_env.data,
            isolated_env.root.parent,
        ):
            with pytest.raises(ValueError):
                validate_astrbot_backup_dir(str(forbidden))

    @pytest.mark.parametrize(
        "rel_subpath",
        [
            "plugins",
            "plugins/backups",
            "plugin_data",
            "plugin_data/my_plugin/backups",
            "config",
            "config/sub",
            "t2i_templates",
            "webchat",
            "temp",
            "temp/exports",
            "skills",
            "knowledge_base",
            "knowledge_base/kb1/backups",
            "attachments",
            "attachments/sub",
            "workspaces",
            "workspaces/session1",
            "logs",
            "dist",
        ],
    )
    def test_rejects_backed_up_and_managed_subdirectories(
        self, isolated_env, rel_subpath: str
    ):
        # Both absolute and relative paths into backed-up dirs must be rejected.
        with pytest.raises(ValueError, match="overlap|backed-up"):
            validate_astrbot_backup_dir(str(isolated_env.data / rel_subpath))
        with pytest.raises(ValueError, match="overlap|backed-up"):
            validate_astrbot_backup_dir(rel_subpath)

    def test_rejects_control_chars_and_existing_file(self, isolated_env):
        with pytest.raises(ValueError, match="control characters"):
            validate_astrbot_backup_dir("bad\x00dir")
        with pytest.raises(ValueError, match="control characters"):
            validate_astrbot_backup_dir("bad\ndir")

        regular_file = isolated_env.tmp_path / "already_a_file.txt"
        regular_file.write_text("hello", encoding="utf-8")
        with pytest.raises(ValueError, match="existing file"):
            validate_astrbot_backup_dir(str(regular_file), check_writable=True)

    def test_rejects_windows_specific_invalid_paths_or_cross_os_drive(
        self, isolated_env, monkeypatch: pytest.MonkeyPatch
    ):
        if os.name == "nt":
            with pytest.raises(ValueError, match="Drive-relative"):
                validate_astrbot_backup_dir("D:backups")
            for driveless in ("/backups", r"\backups", "/data/backups"):
                with pytest.raises(ValueError, match="Root-relative Windows paths"):
                    validate_astrbot_backup_dir(driveless)
            for incomplete in (r"\\backups", "//backups"):
                with pytest.raises(ValueError, match="Incomplete Windows path anchor"):
                    validate_astrbot_backup_dir(incomplete)
            # Valid UNC subdirectory passes syntax validation (without hitting disk).
            unc_resolved = validate_astrbot_backup_dir(
                r"\\example-nas\share\astrbot-backups", check_writable=False
            )
            assert unc_resolved.lower().endswith("astrbot-backups")
            with pytest.raises(ValueError, match="invalid characters"):
                validate_astrbot_backup_dir(str(isolated_env.tmp_path / "bad*dir"))
            with pytest.raises(ValueError, match="reserved Windows device name"):
                validate_astrbot_backup_dir(str(isolated_env.tmp_path / "CON"))
        monkeypatch.setattr("astrbot.core.utils.astrbot_path.os.name", "posix")
        with pytest.raises(ValueError, match="Windows drive-letter"):
            validate_astrbot_backup_dir(r"D:\AstrBotBackups\exports")

    def test_rejects_unwritable_dir_and_cleans_up_new_empty_dir(
        self, isolated_env, monkeypatch: pytest.MonkeyPatch
    ):
        target = isolated_env.tmp_path / "unwritable_new_dir"

        def _deny_mkstemp(*args, **kwargs):
            raise PermissionError("read-only filesystem")

        monkeypatch.setattr(
            "astrbot.core.utils.astrbot_path.tempfile.mkstemp", _deny_mkstemp
        )
        with pytest.raises(ValueError, match="not writable"):
            validate_astrbot_backup_dir(str(target), check_writable=True)
        assert not target.exists()

    def test_rejects_symlink_pointing_into_backed_up_dir(
        self, isolated_env, monkeypatch: pytest.MonkeyPatch
    ):
        plugin_dir = isolated_env.data / "plugins"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        tricky = isolated_env.tmp_path / "tricky_link"
        real_realpath = os.path.realpath

        def _fake_realpath(p):
            if str(p) == str(tricky):
                return real_realpath(str(plugin_dir / "nested"))
            return real_realpath(p)

        monkeypatch.setattr(
            "astrbot.core.utils.astrbot_path.os.path.realpath", _fake_realpath
        )
        with pytest.raises(ValueError, match="overlap|backed-up"):
            validate_astrbot_backup_dir(str(tricky))

    def test_config_service_validate_config_rejects_recursive_backup_dir(
        self, isolated_env
    ):
        import copy

        valid_cfg = copy.deepcopy(DEFAULT_CONFIG)
        valid_cfg["backup_dir"] = str(isolated_env.tmp_path / "safe_backups")
        errors, _ = validate_config(valid_cfg, CONFIG_METADATA_2, is_core=True)
        assert errors == []

        bad_cfg = copy.deepcopy(DEFAULT_CONFIG)
        bad_cfg["backup_dir"] = "plugins/backups"
        errors, _ = validate_config(bad_cfg, CONFIG_METADATA_2, is_core=True)
        assert any("backup_dir" in e for e in errors)


class TestBackupServiceCustomDirectory:
    def test_default_settings_and_custom_update_and_reset(self, isolated_env):
        service = isolated_env.service
        default_dir = get_default_astrbot_backups_path()

        initial = service.get_backup_settings()
        assert initial["backup_dir"] == ""
        assert initial["effective_backup_dir"] == default_dir
        assert initial["default_backup_dir"] == default_dir
        assert initial["is_custom"] is False
        assert initial["source"] == "default"
        assert initial["env_override"] is False
        assert initial["is_valid"] is True
        assert initial["validation_error"] is None

        custom_dir = isolated_env.tmp_path / "d_drive_exports"
        updated = service.update_backup_settings({"backup_dir": str(custom_dir)})
        assert updated["is_custom"] is True
        assert updated["source"] == "config"
        assert updated["effective_backup_dir"] == os.path.realpath(str(custom_dir))
        assert custom_dir.is_dir()
        assert isolated_env.config["backup_dir"] == os.path.normpath(str(custom_dir))
        assert isolated_env.config.save_calls >= 2
        assert (
            service.chunked_uploads.chunks_root
            == Path(updated["effective_backup_dir"]) / ".chunks"
        )

        # Reset via empty string restores default cleanly.
        reset = service.update_backup_settings({"backup_dir": ""})
        assert reset["backup_dir"] == ""
        assert reset["is_custom"] is False
        assert reset["source"] == "default"
        assert reset["effective_backup_dir"] == default_dir
        assert service.chunked_uploads.chunks_root == Path(default_dir) / ".chunks"

    def test_env_override_blocks_ui_updates(
        self, isolated_env, monkeypatch: pytest.MonkeyPatch
    ):
        env_dir = isolated_env.tmp_path / "env_backup_dir"
        monkeypatch.setenv(ASTRBOT_BACKUP_DIR_ENV, str(env_dir))

        settings = isolated_env.service.get_backup_settings()
        assert settings["env_override"] is True
        assert settings["source"] == "env"
        assert settings["effective_backup_dir"] == os.path.realpath(str(env_dir))

        with pytest.raises(BackupServiceError, match=ASTRBOT_BACKUP_DIR_ENV):
            isolated_env.service.update_backup_settings(
                {"backup_dir": str(isolated_env.tmp_path / "other")}
            )

    def test_active_tasks_and_uploads_block_directory_switch(self, isolated_env):
        service = isolated_env.service
        target = str(isolated_env.tmp_path / "new_dir")

        # 1. Active export/import task blocks switch.
        service._init_task("task-export", "export", "processing")
        assert service.get_backup_settings()["has_active_tasks"] is True
        with pytest.raises(BackupServiceError, match="in progress"):
            service.update_backup_settings({"backup_dir": target})
        service._set_task_result("task-export", "completed", result={})
        assert service.get_backup_settings()["has_active_tasks"] is False

        # 2. Active direct upload blocks switch.
        service._active_direct_uploads = 1
        with pytest.raises(BackupServiceError, match="in progress"):
            service.update_backup_settings({"backup_dir": target})
        service._active_direct_uploads = 0

        # 3. Active chunked upload blocks switch, expired session does not.
        session_info = service.upload_init(
            {"filename": "test.zip", "total_size": 100}, owner="alice"
        )
        with pytest.raises(BackupServiceError, match="in progress"):
            service.update_backup_settings({"backup_dir": target})

        inner = service.chunked_uploads.get_session(
            session_info["upload_id"], owner="alice"
        )
        inner.last_activity -= service.chunked_uploads.expire_seconds + 10
        updated = service.update_backup_settings({"backup_dir": target})
        assert updated["effective_backup_dir"] == os.path.realpath(target)

    @pytest.mark.asyncio
    async def test_export_list_download_rename_delete_and_old_dir_preservation(
        self, isolated_env
    ):
        service = isolated_env.service
        default_dir = Path(get_default_astrbot_backups_path())
        old_zip = _create_valid_backup_zip(default_dir / "old_backup.zip")

        custom_dir = isolated_env.tmp_path / "custom_exports"
        service.update_backup_settings({"backup_dir": str(custom_dir)})

        # Old backup stays untouched in default_dir and is not listed in custom_dir.
        assert old_zip.exists()
        listed_empty = service.list_backups(page=1, page_size=20)
        assert listed_empty["total"] == 0
        assert listed_empty["backup_dir"] == os.path.realpath(str(custom_dir))

        # Trigger export into custom_dir.
        export_resp = service.export_backup()
        assert export_resp["backup_dir"] == os.path.realpath(str(custom_dir))
        task_id = export_resp["task_id"]

        for _ in range(100):
            prog = service.get_progress(task_id)
            if prog["status"] in ("completed", "failed"):
                break
            await asyncio.sleep(0.05)

        prog = service.get_progress(task_id)
        assert prog["status"] == "completed", prog.get("error")
        exported_filename = prog["result"]["filename"]
        exported_path = Path(prog["result"]["path"])
        assert exported_path.parent == Path(os.path.realpath(str(custom_dir)))
        assert prog["result"]["backup_dir"] == os.path.realpath(str(custom_dir))
        assert exported_path.is_file()

        # List, download, rename, check, and delete operate on custom_dir.
        listed = service.list_backups(page=1, page_size=20)
        assert listed["total"] == 1
        assert listed["items"][0]["filename"] == exported_filename

        token = jwt.encode(
            {"username": "astrbot", "exp": 4_102_444_800},
            JWT_SECRET,
            algorithm="HS256",
        )
        dl = service.prepare_download(
            filename=exported_filename, token=token, jwt_secret=JWT_SECRET
        )
        assert Path(dl.path) == exported_path

        precheck = service.check_backup({"filename": exported_filename})
        assert precheck["valid"] is True

        renamed = service.rename_backup(
            {"filename": exported_filename, "new_name": "renamed_backup"}
        )
        assert renamed["new_filename"] == "renamed_backup.zip"
        assert (custom_dir / "renamed_backup.zip").is_file()

        # Path traversal and dotfile access are rejected.
        for bad_name in ("../old_backup.zip", ".chunks", "sub/a.zip", "a\x00.zip"):
            with pytest.raises(BackupServiceError):
                service.delete_backup({"filename": bad_name})

        service.delete_backup({"filename": "renamed_backup.zip"})
        assert not (custom_dir / "renamed_backup.zip").exists()

        # Switching back to default reveals old_backup.zip untouched.
        service.update_backup_settings({"backup_dir": ""})
        restored_list = service.list_backups(page=1, page_size=20)
        assert [item["filename"] for item in restored_list["items"]] == [
            "old_backup.zip"
        ]

    @pytest.mark.asyncio
    async def test_chunked_upload_writes_to_custom_directory(self, isolated_env):
        service = isolated_env.service
        custom_dir = isolated_env.tmp_path / "custom_uploads"
        service.update_backup_settings({"backup_dir": str(custom_dir)})

        sample_zip_path = _create_valid_backup_zip(
            isolated_env.tmp_path / "source_upload.zip"
        )
        payload_bytes = sample_zip_path.read_bytes()

        init_res = service.upload_init(
            {"filename": "uploaded.zip", "total_size": len(payload_bytes)},
            owner="astrbot",
        )
        upload_id = init_res["upload_id"]
        assert (custom_dir / ".chunks" / upload_id).is_dir()

        await service.upload_chunk(
            upload_id=upload_id,
            chunk_index_str="0",
            chunk_file=_StubUploadFile("part0", payload_bytes),
            owner="astrbot",
        )
        complete_res = await service.upload_complete(
            {"upload_id": upload_id}, owner="astrbot"
        )
        final_path = Path(complete_res["path"])
        assert final_path.parent == Path(os.path.realpath(str(custom_dir)))
        assert final_path.is_file()
        assert complete_res["backup_dir"] == os.path.realpath(str(custom_dir))

    def test_hand_edited_invalid_config_reports_error_in_settings_and_blocks_list(
        self, isolated_env
    ):
        isolated_env.config["backup_dir"] = "plugins/recursive_trap"
        settings = isolated_env.service.get_backup_settings()
        assert settings["is_valid"] is False
        assert settings["validation_error"]
        assert settings["effective_backup_dir"] == get_default_astrbot_backups_path()

        with pytest.raises(BackupServiceError, match="overlap|backed-up"):
            isolated_env.service.list_backups(page=1, page_size=10)

        # User can recover by resetting via update_backup_settings.
        fixed = isolated_env.service.update_backup_settings({"backup_dir": ""})
        assert fixed["is_valid"] is True
        assert fixed["source"] == "default"

    def test_list_backups_skips_symlink_escaping_backup_dir(
        self, isolated_env, monkeypatch: pytest.MonkeyPatch
    ):
        service = isolated_env.service
        custom_dir = isolated_env.tmp_path / "list_target"
        service.update_backup_settings({"backup_dir": str(custom_dir)})

        inside_zip = _create_valid_backup_zip(custom_dir / "legit.zip")
        outside_zip = _create_valid_backup_zip(isolated_env.tmp_path / "secret.zip")
        escaped_entry = custom_dir / "escaped.zip"
        escaped_entry.write_bytes(b"placeholder")

        real_resolve = Path.resolve

        def _fake_resolve(self_path: Path, strict: bool = False) -> Path:
            if self_path.name == "escaped.zip":
                return real_resolve(outside_zip, strict=False)
            return real_resolve(self_path, strict=strict)

        monkeypatch.setattr(Path, "resolve", _fake_resolve)
        listed = service.list_backups(page=1, page_size=20)
        assert [item["filename"] for item in listed["items"]] == [inside_zip.name]

    def test_update_backup_settings_rolls_back_on_save_config_error(
        self, isolated_env, monkeypatch: pytest.MonkeyPatch
    ):
        service = isolated_env.service
        initial_dir = isolated_env.tmp_path / "initial_exports"
        service.update_backup_settings({"backup_dir": str(initial_dir)})
        prev_config_val = isolated_env.config["backup_dir"]
        prev_chunks_root = service.chunked_uploads.chunks_root

        next_dir = isolated_env.tmp_path / "failed_save_exports"

        def _fail_save():
            raise OSError("disk full while saving cmd_config.json")

        monkeypatch.setattr(isolated_env.config, "save_config", _fail_save)
        with pytest.raises(OSError, match="disk full"):
            service.update_backup_settings({"backup_dir": str(next_dir)})

        assert isolated_env.config["backup_dir"] == prev_config_val
        assert service.chunked_uploads.chunks_root == prev_chunks_root
        assert service.get_backup_settings()[
            "effective_backup_dir"
        ] == os.path.realpath(str(initial_dir))

        # Also verify rollback when backup_dir key was originally absent and override was set.
        isolated_env.config.pop("backup_dir", None)
        override_dir = str(isolated_env.tmp_path / "override_exports")
        service.backup_dir = override_dir
        with pytest.raises(OSError, match="disk full"):
            service.update_backup_settings({"backup_dir": str(next_dir)})
        assert "backup_dir" not in isolated_env.config
        assert service._backup_dir_override == override_dir


class TestBackupSettingsHttpApi:
    @pytest.mark.asyncio
    async def test_v1_and_legacy_backup_settings_routes(self, isolated_env):
        app = FastAPI()
        app.state.jwt_secret = JWT_SECRET
        app.state.services = SimpleNamespace(backups=isolated_env.service)
        app.include_router(backups_router, prefix="/api/v1")
        app.include_router(legacy_backups_router)

        token = jwt.encode(
            {"username": "astrbot", "exp": 4_102_444_800},
            JWT_SECRET,
            algorithm="HS256",
        )
        headers = {"Authorization": f"Bearer {token}"}

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            # GET /api/v1/backups/settings must NOT be swallowed by /backups/{filename:path}.
            resp = await client.get("/api/v1/backups/settings", headers=headers)
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "ok"
            assert body["data"]["source"] == "default"

            # PUT valid custom directory.
            custom_dir = isolated_env.tmp_path / "api_custom_backups"
            put_resp = await client.put(
                "/api/v1/backups/settings",
                headers=headers,
                json={"backup_dir": str(custom_dir)},
            )
            assert put_resp.status_code == 200
            put_body = put_resp.json()
            assert put_body["status"] == "ok"
            assert put_body["data"]["is_custom"] is True
            assert put_body["data"]["effective_backup_dir"] == os.path.realpath(
                str(custom_dir)
            )

            # GET /api/v1/backups includes backup_dir.
            list_resp = await client.get("/api/v1/backups", headers=headers)
            assert list_resp.status_code == 200
            assert list_resp.json()["data"]["backup_dir"] == os.path.realpath(
                str(custom_dir)
            )

            # PUT invalid recursive directory returns status=error.
            bad_resp = await client.put(
                "/api/v1/backups/settings",
                headers=headers,
                json={"backup_dir": "plugins/evil"},
            )
            assert bad_resp.status_code == 200
            assert bad_resp.json()["status"] == "error"

            # PUT null resets to default.
            reset_resp = await client.put(
                "/api/v1/backups/settings",
                headers=headers,
                json={"backup_dir": None},
            )
            assert reset_resp.status_code == 200
            assert reset_resp.json()["data"]["source"] == "default"

            # Legacy GET/POST /api/backup/settings also work.
            legacy_get = await client.get("/api/backup/settings", headers=headers)
            assert legacy_get.status_code == 200
            assert legacy_get.json()["status"] == "ok"

            legacy_post = await client.post(
                "/api/backup/settings",
                headers=headers,
                json={"backup_dir": str(custom_dir)},
            )
            assert legacy_post.status_code == 200
            assert legacy_post.json()["data"]["is_custom"] is True
