import os
import sys
from collections import namedtuple

# 将项目根目录添加到 sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest import mock

import pytest

from main import check_dashboard_files, check_env


def _make_version_info(major: int, minor: int):
    version_info_cls = namedtuple(
        "VersionInfo",
        ["major", "minor", "micro", "releaselevel", "serial"],
    )
    return version_info_cls(major, minor, 0, "final", 0)


def test_check_env(monkeypatch):
    version_info_correct = _make_version_info(3, 10)
    version_info_wrong = _make_version_info(3, 9)
    monkeypatch.setattr(sys, "version_info", version_info_correct, raising=False)

    expected_paths = {
        "root": "/tmp/astrbot-root",
        "site_packages": "/tmp/astrbot-root/data/plugins/_site",
        "config": "/tmp/astrbot-root/data/config",
        "plugins": "/tmp/astrbot-root/data/plugins",
        "temp": "/tmp/astrbot-root/data/temp",
        "knowledge_base": "/tmp/astrbot-root/data/knowledge_base",
    }
    monkeypatch.setattr("main.get_astrbot_root", lambda: expected_paths["root"])
    monkeypatch.setattr(
        "main.get_astrbot_site_packages_path",
        lambda: expected_paths["site_packages"],
    )
    monkeypatch.setattr(
        "main.get_astrbot_config_path", lambda: expected_paths["config"]
    )
    monkeypatch.setattr(
        "main.get_astrbot_plugin_path", lambda: expected_paths["plugins"]
    )
    monkeypatch.setattr("main.get_astrbot_temp_path", lambda: expected_paths["temp"])
    monkeypatch.setattr(
        "main.get_astrbot_knowledge_base_path",
        lambda: expected_paths["knowledge_base"],
    )

    with mock.patch("os.makedirs") as mock_makedirs:
        check_env()
        for path in (
            expected_paths["config"],
            expected_paths["plugins"],
            expected_paths["temp"],
            expected_paths["knowledge_base"],
            expected_paths["site_packages"],
        ):
            mock_makedirs.assert_any_call(path, exist_ok=True)

    monkeypatch.setattr(sys, "version_info", version_info_wrong, raising=False)
    with pytest.raises(SystemExit):
        check_env()


@pytest.mark.asyncio
async def test_check_dashboard_files_not_exists(monkeypatch):
    """Tests dashboard download when files do not exist."""
    monkeypatch.setattr(os.path, "exists", lambda x: False)

    with mock.patch("main.download_dashboard") as mock_download:
        await check_dashboard_files()
        mock_download.assert_called_once()


@pytest.mark.asyncio
async def test_check_dashboard_files_exists_and_version_match(monkeypatch):
    """Tests that dashboard is not downloaded when it exists and version matches."""
    # Mock os.path.exists to return True
    monkeypatch.setattr(os.path, "exists", lambda x: True)

    # Mock get_dashboard_version to return the current version
    with mock.patch("main.get_dashboard_version") as mock_get_version:
        # We need to import VERSION from main's context
        from main import VERSION

        mock_get_version.return_value = f"v{VERSION}"

        with mock.patch("main.download_dashboard") as mock_download:
            await check_dashboard_files()
            # Assert that download_dashboard was NOT called
            mock_download.assert_not_called()


@pytest.mark.asyncio
async def test_check_dashboard_files_exists_but_version_mismatch(monkeypatch):
    """Tests that a warning is logged when dashboard version mismatches."""
    monkeypatch.setattr(os.path, "exists", lambda x: True)

    with mock.patch("main.get_dashboard_version") as mock_get_version:
        mock_get_version.return_value = "v0.0.1"  # A different version

        with mock.patch("main.logger.warning") as mock_logger_warning:
            await check_dashboard_files()
            mock_logger_warning.assert_called_once()
            call_args, _ = mock_logger_warning.call_args
            assert "不符" in call_args[0]


@pytest.mark.asyncio
async def test_check_dashboard_files_with_webui_dir_arg(monkeypatch):
    """Tests that providing a valid webui_dir skips all checks."""
    valid_dir = "/tmp/my-custom-webui"
    monkeypatch.setattr(os.path, "exists", lambda path: path == valid_dir)

    with mock.patch("main.download_dashboard") as mock_download:
        with mock.patch("main.get_dashboard_version") as mock_get_version:
            result = await check_dashboard_files(webui_dir=valid_dir)
            assert result == valid_dir
            mock_download.assert_not_called()
            mock_get_version.assert_not_called()
