import os
import sys
from pathlib import Path

# 将项目根目录添加到 sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest import mock

import pytest

from astrbot.core.utils.io import get_dashboard_version, should_use_bundled_dashboard_dist
from main import (
    DASHBOARD_RESET_PASSWORD_ENV,
    _apply_startup_env_flags,
    check_dashboard_files,
    check_env,
)


class _version_info:
    def __init__(self, major, minor):
        self.major = major
        self.minor = minor

    def __eq__(self, other):
        if isinstance(other, tuple):
            return (self.major, self.minor) == other[:2]
        return (self.major, self.minor) == (other.major, other.minor)

    def __ge__(self, other):
        if isinstance(other, tuple):
            return (self.major, self.minor) >= other[:2]
        return (self.major, self.minor) >= (other.major, other.minor)

    def __le__(self, other):
        if isinstance(other, tuple):
            return (self.major, self.minor) <= other[:2]
        return (self.major, self.minor) <= (other.major, other.minor)

    def __gt__(self, other):
        if isinstance(other, tuple):
            return (self.major, self.minor) > other[:2]
        return (self.major, self.minor) > (other.major, other.minor)

    def __lt__(self, other):
        if isinstance(other, tuple):
            return (self.major, self.minor) < other[:2]
        return (self.major, self.minor) < (other.major, other.minor)


def test_check_env(monkeypatch):
    version_info_correct = _version_info(3, 10)
    version_info_wrong = _version_info(3, 9)
    monkeypatch.setattr(sys, "version_info", version_info_correct)
    with mock.patch("os.makedirs") as mock_makedirs:
        check_env()
        # check_env uses get_astrbot_*_path() which returns absolute paths,
        # so just verify makedirs was called the expected number of times
        assert mock_makedirs.call_count >= 4
        # Verify all calls used exist_ok=True
        for call_args in mock_makedirs.call_args_list:
            assert call_args[1].get("exist_ok") is True

    monkeypatch.setattr(sys, "version_info", version_info_wrong)
    with pytest.raises(SystemExit):
        check_env()


def test_apply_startup_env_flags_sets_reset_password_env(monkeypatch):
    monkeypatch.delenv(DASHBOARD_RESET_PASSWORD_ENV, raising=False)

    _apply_startup_env_flags(["--webui-dir", "/tmp/webui", "--reset-password"])

    assert os.environ[DASHBOARD_RESET_PASSWORD_ENV] == "1"


def test_apply_startup_env_flags_ignores_unrelated_args(monkeypatch):
    monkeypatch.delenv(DASHBOARD_RESET_PASSWORD_ENV, raising=False)

    _apply_startup_env_flags(["--webui-dir", "/tmp/webui"])

    assert DASHBOARD_RESET_PASSWORD_ENV not in os.environ


def test_apply_startup_env_flags_does_not_reset_for_help(monkeypatch):
    monkeypatch.delenv(DASHBOARD_RESET_PASSWORD_ENV, raising=False)

    _apply_startup_env_flags(["--reset-password", "--help"])

    assert DASHBOARD_RESET_PASSWORD_ENV not in os.environ


def test_check_env_appends_user_site_packages_after_runtime_paths(monkeypatch):
    astrbot_root = "/tmp/astrbot-root"
    site_packages_path = "/tmp/astrbot-site-packages"
    original_sys_path = list(sys.path)

    monkeypatch.setattr(sys, "version_info", _version_info(3, 12))
    monkeypatch.setattr("main.get_astrbot_root", lambda: astrbot_root)
    monkeypatch.setattr(
        "main.get_astrbot_site_packages_path", lambda: site_packages_path
    )
    monkeypatch.setattr("main.get_astrbot_config_path", lambda: "/tmp/config")
    monkeypatch.setattr("main.get_astrbot_plugin_path", lambda: "/tmp/plugins")
    monkeypatch.setattr("main.get_astrbot_temp_path", lambda: "/tmp/temp")
    monkeypatch.setattr("main.get_astrbot_knowledge_base_path", lambda: "/tmp/kb")
    monkeypatch.setattr(sys, "path", ["/runtime/lib", *original_sys_path])

    with mock.patch("os.makedirs"):
        check_env()

    assert sys.path[0] == astrbot_root
    assert sys.path[-1] == site_packages_path
    assert sys.path.index(site_packages_path) > sys.path.index("/runtime/lib")


def test_check_env_does_not_append_duplicate_user_site_packages(monkeypatch):
    astrbot_root = "/tmp/astrbot-root"
    site_packages_path = "/tmp/astrbot-site-packages"
    original_sys_path = list(sys.path)

    monkeypatch.setattr(sys, "version_info", _version_info(3, 12))
    monkeypatch.setattr("main.get_astrbot_root", lambda: astrbot_root)
    monkeypatch.setattr(
        "main.get_astrbot_site_packages_path", lambda: site_packages_path
    )
    monkeypatch.setattr("main.get_astrbot_config_path", lambda: "/tmp/config")
    monkeypatch.setattr("main.get_astrbot_plugin_path", lambda: "/tmp/plugins")
    monkeypatch.setattr("main.get_astrbot_temp_path", lambda: "/tmp/temp")
    monkeypatch.setattr("main.get_astrbot_knowledge_base_path", lambda: "/tmp/kb")
    monkeypatch.setattr(
        sys, "path", [astrbot_root, *original_sys_path, site_packages_path]
    )

    with mock.patch("os.makedirs"):
        check_env()

    assert sys.path.count(site_packages_path) == 1


def test_version_info_comparisons():
    """Test _version_info comparison operators with tuples and other instances."""
    v3_10 = _version_info(3, 10)
    v3_9 = _version_info(3, 9)
    v3_11 = _version_info(3, 11)

    # Test __eq__ with tuples
    assert v3_10 == (3, 10)
    assert v3_10 != (3, 9)
    assert v3_9 == (3, 9)

    # Test __ge__ with tuples
    assert v3_10 >= (3, 10)
    assert v3_10 >= (3, 9)
    assert not (v3_9 >= (3, 10))
    assert v3_11 >= (3, 10)

    # Test __eq__ with other _version_info instances
    assert v3_10 == _version_info(3, 10)
    assert v3_10 != v3_9
    assert v3_10 == v3_10  # Same instance

    assert v3_10 != v3_11

    # Test __ge__ with other _version_info instances
    assert v3_10 >= v3_10
    assert v3_10 >= v3_9
    assert not (v3_9 >= v3_10)
    assert v3_11 >= v3_10

    assert v3_11 >= v3_11  # Same instance


@pytest.mark.asyncio
async def test_check_dashboard_files_not_exists(tmp_path):
    """Tests dashboard download when files do not exist."""
    data_dir = tmp_path / "data"
    bundled_dist = tmp_path / "bundled-dist"

    with mock.patch("main.get_astrbot_data_path", return_value=str(data_dir)):
        with mock.patch(
            "main.get_bundled_dashboard_dist_path",
            return_value=bundled_dist,
        ):
            with mock.patch("main.download_dashboard") as mock_download:
                result = await check_dashboard_files()

        from main import VERSION

        assert result == str(data_dir / "dist")
        mock_download.assert_called_once()
        mock_download.assert_called_once_with(
            version=f"v{VERSION}",
            latest=False,
            allow_insecure_ssl_fallback=False,
        )


@pytest.mark.asyncio
async def test_check_dashboard_files_exists_and_version_match(tmp_path):
    """Tests that dashboard is not downloaded when it exists and version matches."""
    from main import VERSION

    data_dir = tmp_path / "data"
    data_dist = data_dir / "dist"
    (data_dist / "assets").mkdir(parents=True)
    (data_dist / "assets" / "version").write_text(f"v{VERSION}", encoding="utf-8")
    (data_dist / "index.html").write_text("user", encoding="utf-8")

    with mock.patch("main.get_astrbot_data_path", return_value=str(data_dir)):
        with mock.patch("main.download_dashboard") as mock_download:
            result = await check_dashboard_files()
            assert result == str(data_dist)
            mock_download.assert_not_called()


@pytest.mark.asyncio
async def test_check_dashboard_files_exists_but_version_mismatch_downloads(tmp_path):
    """Tests that a mismatched dashboard is downloaded on startup."""
    from main import VERSION

    data_dir = tmp_path / "data"
    data_dist = data_dir / "dist"
    bundled_dist = tmp_path / "bundled-dist"
    (data_dist / "assets").mkdir(parents=True)
    (data_dist / "assets" / "version").write_text("v0.0.1", encoding="utf-8")

    with mock.patch("main.get_astrbot_data_path", return_value=str(data_dir)):
        with mock.patch(
            "main.get_bundled_dashboard_dist_path",
            return_value=bundled_dist,
        ):
            with mock.patch("main.download_dashboard") as mock_download:
                with mock.patch("main.logger.warning") as mock_logger_warning:
                    result = await check_dashboard_files()

            assert result == str(data_dist)
            mock_download.assert_called_once_with(
                version=f"v{VERSION}",
                latest=False,
                allow_insecure_ssl_fallback=False,
            )
            mock_logger_warning.assert_called_once()
            call_args, _ = mock_logger_warning.call_args
            assert "WebUI version mismatch" in call_args[0]


@pytest.mark.asyncio
async def test_check_dashboard_files_falls_back_to_stale_dist_when_download_fails(
    tmp_path,
):
    """Tests stale dashboard fallback when the matching WebUI cannot be downloaded."""
    from main import VERSION

    data_dir = tmp_path / "data"
    data_dist = data_dir / "dist"
    bundled_dist = tmp_path / "bundled-dist"
    (data_dist / "assets").mkdir(parents=True)
    (data_dist / "assets" / "version").write_text("v0.0.1", encoding="utf-8")
    (data_dist / "index.html").write_text("stale", encoding="utf-8")

    with mock.patch("main.get_astrbot_data_path", return_value=str(data_dir)):
        with mock.patch(
            "main.get_bundled_dashboard_dist_path",
            return_value=bundled_dist,
        ):
            with mock.patch(
                "main.download_dashboard",
                side_effect=RuntimeError("missing dashboard asset"),
            ) as mock_download:
                with mock.patch("main.logger.warning") as mock_logger_warning:
                    result = await check_dashboard_files()

    assert result == str(data_dist)
    mock_download.assert_called_once_with(
        version=f"v{VERSION}",
        latest=False,
        allow_insecure_ssl_fallback=False,
    )
    assert any(
        "Falling back to existing data/dist WebUI" in call.args[0]
        for call in mock_logger_warning.call_args_list
    )


@pytest.mark.asyncio
async def test_check_dashboard_files_downloads_when_matching_dist_is_incomplete(
    tmp_path,
):
    """Tests that a version match alone is not enough to serve WebUI."""
    from main import VERSION

    data_dir = tmp_path / "data"
    data_dist = data_dir / "dist"
    bundled_dist = tmp_path / "bundled-dist"
    (data_dist / "assets").mkdir(parents=True)
    (data_dist / "assets" / "version").write_text(f"v{VERSION}", encoding="utf-8")

    with mock.patch("main.get_astrbot_data_path", return_value=str(data_dir)):
        with mock.patch(
            "main.get_bundled_dashboard_dist_path",
            return_value=bundled_dist,
        ):
            with mock.patch("main.download_dashboard") as mock_download:
                result = await check_dashboard_files()

    assert result == str(data_dist)
    mock_download.assert_called_once_with(
        version=f"v{VERSION}",
        latest=False,
        allow_insecure_ssl_fallback=False,
    )


def test_should_use_bundled_dashboard_dist_when_data_dist_is_stale(tmp_path):
    user_dist = tmp_path / "user-dist"
    bundled_dist = tmp_path / "bundled-dist"
    (user_dist / "assets").mkdir(parents=True)
    (bundled_dist / "assets").mkdir(parents=True)
    (user_dist / "assets" / "version").write_text("v4.24.2", encoding="utf-8")
    (bundled_dist / "assets" / "version").write_text("v4.24.4", encoding="utf-8")
    (bundled_dist / "index.html").write_text("bundled", encoding="utf-8")

    with mock.patch(
        "astrbot.core.utils.io.get_bundled_dashboard_dist_path",
        return_value=bundled_dist,
    ):
        assert should_use_bundled_dashboard_dist(user_dist, "v4.24.4") is True


def test_should_use_bundled_dashboard_dist_when_version_file_is_malformed(tmp_path):
    user_dist = tmp_path / "user-dist"
    bundled_dist = tmp_path / "bundled-dist"
    (user_dist / "assets").mkdir(parents=True)
    (bundled_dist / "assets").mkdir(parents=True)
    (user_dist / "assets" / "version").write_text("not-a-version", encoding="utf-8")
    (bundled_dist / "assets" / "version").write_text("v4.24.4", encoding="utf-8")
    (bundled_dist / "index.html").write_text("bundled", encoding="utf-8")

    with mock.patch(
        "astrbot.core.utils.io.get_bundled_dashboard_dist_path",
        return_value=bundled_dist,
    ):
        assert should_use_bundled_dashboard_dist(user_dist, "4.24.4") is True


def test_should_use_bundled_dashboard_dist_when_data_version_file_is_missing(tmp_path):
    user_dist = tmp_path / "user-dist"
    bundled_dist = tmp_path / "bundled-dist"
    (user_dist / "assets").mkdir(parents=True)
    (bundled_dist / "assets").mkdir(parents=True)
    (bundled_dist / "assets" / "version").write_text("v4.24.4", encoding="utf-8")
    (bundled_dist / "index.html").write_text("bundled", encoding="utf-8")

    with mock.patch(
        "astrbot.core.utils.io.get_bundled_dashboard_dist_path",
        return_value=bundled_dist,
    ):
        assert should_use_bundled_dashboard_dist(user_dist, "4.24.4") is True


@pytest.mark.asyncio
async def test_get_dashboard_version_uses_bundled_dist_when_data_dist_is_missing(
    tmp_path,
):
    """Tests bundled WebUI version lookup when data/dist is absent."""
    from main import VERSION

    data_dir = tmp_path / "data"
    bundled_dist = tmp_path / "bundled-dist"
    (bundled_dist / "assets").mkdir(parents=True)
    (bundled_dist / "assets" / "version").write_text(f"v{VERSION}", encoding="utf-8")
    (bundled_dist / "index.html").write_text("bundled", encoding="utf-8")

    with mock.patch(
        "astrbot.core.utils.io.get_astrbot_data_path",
        return_value=str(data_dir),
    ):
        with mock.patch(
            "astrbot.core.utils.io.get_bundled_dashboard_dist_path",
            return_value=bundled_dist,
        ):
            assert await get_dashboard_version() == f"v{VERSION}"


@pytest.mark.asyncio
async def test_check_dashboard_files_replaces_stale_data_dist_with_bundled_dist(
    tmp_path,
):
    """Tests that a stale data/dist is repaired from bundled dashboard assets."""
    from main import VERSION

    data_dir = tmp_path / "data"
    data_dist = data_dir / "dist"
    bundled_dist = tmp_path / "bundled-dist"
    (data_dist / "assets").mkdir(parents=True)
    (bundled_dist / "assets").mkdir(parents=True)
    (data_dist / "assets" / "version").write_text("v0.0.1", encoding="utf-8")
    (data_dist / "old.txt").write_text("old", encoding="utf-8")
    (bundled_dist / "assets" / "version").write_text(f"v{VERSION}", encoding="utf-8")
    (bundled_dist / "index.html").write_text("bundled", encoding="utf-8")

    with mock.patch("main.get_astrbot_data_path", return_value=str(data_dir)):
        with mock.patch(
            "main.get_bundled_dashboard_dist_path",
            return_value=Path(bundled_dist),
        ):
            with mock.patch(
                "astrbot.core.utils.io.get_bundled_dashboard_dist_path",
                return_value=Path(bundled_dist),
            ):
                with mock.patch("main.download_dashboard") as mock_download:
                    result = await check_dashboard_files()

    assert result == str(data_dist)
    assert (data_dist / "assets" / "version").read_text(encoding="utf-8") == f"v{VERSION}"
    assert (data_dist / "index.html").read_text(encoding="utf-8") == "bundled"
    assert not (data_dist / "old.txt").exists()
    mock_download.assert_not_called()


@pytest.mark.asyncio
async def test_check_dashboard_files_with_webui_dir_arg(monkeypatch):
    """Tests that providing a valid webui_dir skips all checks."""
    valid_dir = "/tmp/my-custom-webui"
    monkeypatch.setattr(os.path, "exists", lambda path: path == valid_dir)

    with mock.patch("main.download_dashboard") as mock_download:
        with mock.patch("main.get_dashboard_dist_version") as mock_get_version:
            result = await check_dashboard_files(webui_dir=valid_dir)
            assert result == valid_dir
            mock_download.assert_not_called()
            mock_get_version.assert_not_called()
