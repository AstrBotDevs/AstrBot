"""``list_backups`` must tolerate an archive disappearing mid-scan.

The service reads each backup's manifest and only then calls ``os.stat`` on the
same path (``astrbot/dashboard/services/backup_service.py:196-201``). A backup
deleted or renamed in that window raises ``FileNotFoundError``, which propagates
out of the listing, so one concurrent deletion fails the whole backups page
instead of just dropping that entry.
"""

import json
import os
import zipfile
from pathlib import Path

import pytest

from astrbot.dashboard.services.backup_service import BackupService


def write_backup(backup_dir: Path, name: str) -> None:
    """Create a minimal backup archive that carries a readable manifest."""
    with zipfile.ZipFile(backup_dir / name, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps({"origin": "exported", "astrbot_version": "4.0.0"}),
        )


def build_service(backup_dir: Path) -> BackupService:
    service = BackupService.__new__(BackupService)
    service.backup_dir = str(backup_dir)
    service.ensure_cleanup_task_started = lambda: None
    return service


@pytest.mark.parametrize("victim", ["beta.zip", "alpha.zip"])
def test_list_backups_skips_archive_deleted_during_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    victim: str,
) -> None:
    """A vanished archive must be skipped, not fail the whole listing."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    write_backup(backup_dir, "alpha.zip")
    write_backup(backup_dir, "beta.zip")

    real_stat = os.stat

    def racing_stat(path, *args, **kwargs):
        if str(path).endswith(victim):
            raise FileNotFoundError(2, "No such file or directory", str(path))
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(BackupService, "ensure_cleanup_task_started", lambda self: None)
    monkeypatch.setattr(os, "stat", racing_stat)

    result = build_service(backup_dir).list_backups(page=1, page_size=10)

    filenames = [item["filename"] for item in result["items"]]
    assert victim not in filenames
    assert [name for name in filenames if name != victim] == [
        "beta.zip" if victim == "alpha.zip" else "alpha.zip"
    ]
    assert result["total"] == 1
