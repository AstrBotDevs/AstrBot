from pathlib import Path

import pytest

from astrbot.cli.utils.dashboard import DashboardManager


@pytest.mark.asyncio
async def test_dashboard_manager_downloads_to_astrbot_root(monkeypatch, tmp_path):
    manager = DashboardManager()
    manager._bundled_dist = tmp_path / "missing-dist"
    downloaded_paths: list[str] = []

    async def fake_get_dashboard_version():
        return "v0.0.1"

    async def fake_download_dashboard(path, extract_path, version, latest):
        downloaded_paths.append(path)

    monkeypatch.setattr(
        "astrbot.core.utils.io.get_dashboard_version",
        fake_get_dashboard_version,
    )
    monkeypatch.setattr(
        "astrbot.core.utils.io.download_dashboard",
        fake_download_dashboard,
    )

    await manager.ensure_installed(tmp_path)

    assert downloaded_paths == [str(tmp_path / "data" / "dashboard.zip")]
    assert Path(downloaded_paths[0]).is_absolute()
