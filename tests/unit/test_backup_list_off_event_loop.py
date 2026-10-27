"""Backup listing must keep per-file ZIP reads off the event loop thread."""

import json
import threading
import zipfile
from pathlib import Path

import pytest

from astrbot.dashboard.api.backups import list_backups, list_dashboard_backups
from astrbot.dashboard.services.backup_service import BackupService


def write_backup(backup_dir: Path, name: str) -> None:
    """Create a minimal backup archive that carries a readable manifest."""
    with zipfile.ZipFile(backup_dir / name, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps({"origin": "exported", "astrbot_version": "4.0.0"}),
        )


@pytest.mark.asyncio
async def test_list_backups_reads_manifests_off_the_event_loop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every listed backup opens its ZIP; that I/O must not stall the loop.

    The dashboard route awaits ``run_maybe_async`` on a plain callable, so a
    synchronous service method executes directly on the event loop thread.
    """
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    write_backup(backup_dir, "alpha.zip")
    write_backup(backup_dir, "beta.zip")

    real_manifest = BackupService.get_backup_manifest
    manifest_threads: list[int] = []

    def spy(self: BackupService, zip_path: str):
        manifest_threads.append(threading.get_ident())
        return real_manifest(self, zip_path)

    monkeypatch.setattr(BackupService, "get_backup_manifest", spy)

    service = BackupService.__new__(BackupService)
    service.backup_dir = str(backup_dir)
    service.ensure_cleanup_task_started = lambda: None

    loop_thread = threading.get_ident()
    response = await list_backups(
        page=1,
        page_size=10,
        _auth=object(),
        service=service,
    )

    assert response["status"] == "ok"
    assert response["data"]["total"] == 2
    assert len(manifest_threads) == 2, "the ZIP manifest read must actually run"
    assert set(manifest_threads) != {loop_thread}, (
        "backup ZIPs were opened on the event loop thread"
    )


@pytest.mark.asyncio
async def test_legacy_backup_list_reads_manifests_off_the_event_loop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The legacy /api/dashboard/backup/list route shares the same service call."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    write_backup(backup_dir, "gamma.zip")

    real_manifest = BackupService.get_backup_manifest
    manifest_threads: list[int] = []

    def spy(self: BackupService, zip_path: str):
        manifest_threads.append(threading.get_ident())
        return real_manifest(self, zip_path)

    monkeypatch.setattr(BackupService, "get_backup_manifest", spy)

    service = BackupService.__new__(BackupService)
    service.backup_dir = str(backup_dir)
    service.ensure_cleanup_task_started = lambda: None

    loop_thread = threading.get_ident()
    response = await list_dashboard_backups(
        page=1,
        page_size=10,
        _username="admin",
        service=service,
    )

    assert response["status"] == "ok"
    assert len(manifest_threads) == 1
    assert manifest_threads[0] != loop_thread, (
        "backup ZIP was opened on the event loop thread"
    )
