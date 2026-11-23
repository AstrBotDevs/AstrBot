"""Backup filename and task-state behavior using isolated filesystem paths."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from astrbot.dashboard.services import backup_service
from astrbot.dashboard.services.backup_service import (
    CHUNK_SIZE,
    BackupService,
    BackupServiceError,
    generate_unique_filename,
    secure_filename,
)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        (r"C:\private\backup.zip", "backup.zip"),
        (".hidden.zip", "hidden.zip"),
        ("a b?.zip", "a_b_.zip"),
        ("...", "backup"),
        ("", "backup"),
        ("archive.tar.gz", "archive.tar.gz"),
    ],
)
def test_secure_filename_preserves_only_a_safe_basename(filename, expected):
    assert secure_filename(filename) == expected


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("backup.zip", "backup_20261124_001122.zip"),
        ("backup", "backup_20261124_001122"),
        ("archive.tar.gz", "archive.tar_20261124_001122.gz"),
    ],
)
def test_generated_backup_name_uses_the_clock_and_preserves_extension(
    monkeypatch, filename, expected
):
    clock = Mock()
    clock.now.return_value = datetime(2026, 11, 24, 0, 11, 22)
    monkeypatch.setattr(backup_service, "datetime", clock)

    assert generate_unique_filename(filename) == expected
    clock.now.assert_called_once_with()


@pytest.mark.parametrize(
    "filename", ["../private.zip", "dir/file.zip", r"dir\file.zip", "a..zip"]
)
def test_backup_service_rejects_paths_in_api_filenames(filename):
    with pytest.raises(BackupServiceError, match="无效的文件名"):
        BackupService._validate_backup_filename(filename, missing="Missing filename")


def test_backup_service_initializes_task_state_without_existing_data(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        backup_service, "get_astrbot_backups_path", lambda: str(tmp_path / "backups")
    )
    monkeypatch.setattr(
        backup_service, "get_astrbot_data_path", lambda: str(tmp_path / "data")
    )
    service = BackupService(Mock(), SimpleNamespace(astrbot_config={}))

    assert service.backup_dir == str(tmp_path / "backups")
    assert service.data_dir == str(tmp_path / "data")
    assert service.backup_tasks == {}
    assert service.backup_progress == {}
    assert CHUNK_SIZE == 1024 * 1024
    assert service.chunked_uploads.expire_seconds == 3600
    assert service.chunked_uploads.sessions == {}
