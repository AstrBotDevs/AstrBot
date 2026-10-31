"""``list_backups`` must tolerate an archive disappearing mid-scan.

The service reads each backup's manifest and only then calls ``os.stat`` on the
same path (``astrbot/dashboard/services/backup_service.py``). A backup deleted
or renamed in that window raises ``FileNotFoundError``, which propagates out of
the listing, so one concurrent deletion fails the whole backups page instead of
just dropping that entry.

The archive is removed for real right after its manifest has been read, so the
earlier ``os.path.isfile`` guard has already been passed. That keeps the test
dependent on the code path under test rather than on whether the platform's
``os.path.isfile`` happens to call the ``os.stat`` symbol (it does on POSIX,
where ``genericpath.isfile`` looks it up at call time, and it does not on
Windows, where ``ntpath.isfile`` is the ``nt._path_isfile`` builtin).
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

    monkeypatch.setattr(BackupService, "ensure_cleanup_task_started", lambda self: None)
    read_manifest = BackupService.get_backup_manifest

    def read_manifest_then_vanish(self: BackupService, zip_path: str) -> dict | None:
        manifest = read_manifest(self, zip_path)
        if zip_path.endswith(victim):
            # The archive disappears in the window between the manifest read
            # and the stat call, exactly as a concurrent delete would.
            os.remove(zip_path)
        return manifest

    monkeypatch.setattr(BackupService, "get_backup_manifest", read_manifest_then_vanish)

    service = build_service(backup_dir)
    result = service.list_backups(page=1, page_size=10)

    filenames = [item["filename"] for item in result["items"]]
    expected = "alpha.zip" if victim == "beta.zip" else "beta.zip"
    assert victim not in filenames
    assert filenames == [expected]
    assert result["total"] == 1
    assert not (backup_dir / victim).exists()
