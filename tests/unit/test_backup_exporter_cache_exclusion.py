"""Unit tests for backup exporter plugin cache exclusion and unreadable file degradation."""

import logging
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from astrbot.core.backup.exporter import AstrBotExporter


@pytest.mark.asyncio
async def test_export_directories_skips_plugin_caches_but_keeps_code_packages(tmp_path: Path):
    plugins_dir = tmp_path / "plugins"
    plugin_data_dir = tmp_path / "plugin_data"

    # 1) plugin_data/<plugin>/cache/*.mp4 must be excluded; normal DB/config kept.
    vv_data = plugin_data_dir / "astrbot_plugin_video_vision"
    (vv_data / "cache").mkdir(parents=True)
    (vv_data / "cache" / "video.mp4").write_bytes(b"huge-ephemeral-cache")
    (vv_data / ".cache").mkdir(parents=True)
    (vv_data / ".cache" / "tmp.bin").write_bytes(b"ephemeral")
    (vv_data / "settings.json").write_text('{"ok": true}', encoding="utf-8")

    # 2) plugins/<plugin>/cache without __init__.py -> runtime cache (excluded).
    plug_runtime_cache = plugins_dir / "demo_plugin"
    (plug_runtime_cache / "cache").mkdir(parents=True)
    (plug_runtime_cache / "cache" / "thumb.jpg").write_bytes(b"thumb")
    (plug_runtime_cache / ".pytest_cache").mkdir(parents=True)
    (plug_runtime_cache / ".pytest_cache" / "README.md").write_text("pytest", encoding="utf-8")
    (plug_runtime_cache / ".ruff_cache").mkdir(parents=True)
    (plug_runtime_cache / ".ruff_cache" / "CACHEDIR.TAG").write_text("ruff", encoding="utf-8")
    (plug_runtime_cache / "__pycache__").mkdir(parents=True)
    (plug_runtime_cache / "__pycache__" / "main.cpython-312.pyc").write_bytes(b"pyc")
    (plug_runtime_cache / "main.py").write_text("# plugin", encoding="utf-8")

    # 3) plugins/<plugin>/cache WITH __init__.py -> Python package (MUST be kept!).
    plug_pkg = plugins_dir / "pkg_plugin"
    (plug_pkg / "cache").mkdir(parents=True)
    (plug_pkg / "cache" / "__init__.py").write_text("# python package", encoding="utf-8")
    (plug_pkg / "cache" / "store.py").write_text("X = 1", encoding="utf-8")

    exporter = AstrBotExporter(main_db=MagicMock())
    zip_path = tmp_path / "backup.zip"

    with patch(
        "astrbot.core.backup.exporter.get_backup_directories",
        return_value={
            "plugins": str(plugins_dir),
            "plugin_data": str(plugin_data_dir),
        },
    ):
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            stats = await exporter._export_directories(zf)

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())

    assert "directories/plugin_data/astrbot_plugin_video_vision/settings.json" in names
    assert "directories/plugin_data/astrbot_plugin_video_vision/cache/video.mp4" not in names
    assert "directories/plugin_data/astrbot_plugin_video_vision/.cache/tmp.bin" not in names

    assert "directories/plugins/demo_plugin/main.py" in names
    assert "directories/plugins/demo_plugin/cache/thumb.jpg" not in names
    assert "directories/plugins/demo_plugin/.pytest_cache/README.md" not in names
    assert "directories/plugins/demo_plugin/.ruff_cache/CACHEDIR.TAG" not in names
    assert "directories/plugins/demo_plugin/__pycache__/main.cpython-312.pyc" not in names

    # Python package named `cache` is preserved!
    assert "directories/plugins/pkg_plugin/cache/__init__.py" in names
    assert "directories/plugins/pkg_plugin/cache/store.py" in names

    assert stats["plugin_data"]["files"] == 1
    assert stats["plugins"]["files"] == 3


@pytest.mark.asyncio
async def test_export_directories_skips_unreadable_files_with_single_summary_warning(
    tmp_path: Path, caplog
):
    plugin_data_dir = tmp_path / "plugin_data"
    app_dir = plugin_data_dir / "sample_plugin"
    app_dir.mkdir(parents=True)
    good_file = app_dir / "ok.json"
    good_file.write_text('{"good": 1}', encoding="utf-8")
    locked_files = [app_dir / f"locked_{i}.dat" for i in range(7)]
    for path in locked_files:
        path.write_bytes(b"locked")

    exporter = AstrBotExporter(main_db=MagicMock())
    zip_path = tmp_path / "backup.zip"
    real_write = zipfile.ZipFile.write

    def flaky_write(self, filename, arcname=None, *args, **kwargs):
        if Path(filename).name.startswith("locked_"):
            raise PermissionError(13, "Permission denied", str(filename))
        return real_write(self, filename, arcname, *args, **kwargs)

    with (
        patch(
            "astrbot.core.backup.exporter.get_backup_directories",
            return_value={"plugin_data": str(plugin_data_dir)},
        ),
        patch.object(zipfile.ZipFile, "write", flaky_write),
        caplog.at_level(logging.WARNING),
    ):
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            stats = await exporter._export_directories(zf)

    with zipfile.ZipFile(zip_path, "r") as zf:
        assert zf.namelist() == ["directories/plugin_data/sample_plugin/ok.json"]

    # Stats count only files actually archived, not failed ones.
    assert stats["plugin_data"]["files"] == 1
    assert stats["plugin_data"]["size"] == good_file.stat().st_size

    # Exactly ONE aggregated warning (not 7 individual warnings).
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "7" in warnings[0].message
