import os
import sys

# 将项目根目录添加到 sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest import mock

import pytest

from astrbot.core.dashboard_assets import (
    _should_use_bundled_dist,
    get_dashboard_version,
    resolve_dashboard_dist,
)
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


def _write_dashboard_dist(dist_path, version: str | None = None) -> None:
    assets = dist_path / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (dist_path / "index.html").write_text(
        '<script type="module" src="/assets/app.js"></script>',
        encoding="utf-8",
    )
    (assets / "app.js").write_text("export {};", encoding="utf-8")
    if version is not None:
        (assets / "version").write_text(version, encoding="utf-8")


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
async def test_check_dashboard_files_delegates_to_updater(monkeypatch, tmp_path):
    """Startup should depend only on the updater's Dashboard contract."""
    dashboard_path = tmp_path / "dist"
    from astrbot.core.config.default import VERSION

    _write_dashboard_dist(dashboard_path, f"v{VERSION}")
    monkeypatch.setattr(
        "astrbot.core.dashboard_assets.get_astrbot_data_path",
        lambda: str(tmp_path),
    )
    ensure_dashboard = mock.AsyncMock(return_value=dashboard_path)
    monkeypatch.setattr(
        "main.AstrBotUpdater",
        lambda: mock.Mock(ensure_dashboard=ensure_dashboard),
    )

    result = await check_dashboard_files()

    assert result == str(dashboard_path)
    ensure_dashboard.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_check_dashboard_files_returns_none_when_updater_fails(monkeypatch):
    """Startup should fail cleanly when no Dashboard can be prepared."""
    ensure_dashboard = mock.AsyncMock(side_effect=RuntimeError("unavailable"))
    monkeypatch.setattr(
        "main.AstrBotUpdater",
        lambda: mock.Mock(ensure_dashboard=ensure_dashboard),
    )

    assert await check_dashboard_files() is None


def test_should_use_bundled_dashboard_dist_when_data_dist_is_stale(tmp_path):
    user_dist = tmp_path / "user-dist"
    bundled_dist = tmp_path / "bundled-dist"
    (user_dist / "assets").mkdir(parents=True)
    (bundled_dist / "assets").mkdir(parents=True)
    (user_dist / "assets" / "version").write_text("v4.24.2", encoding="utf-8")
    _write_dashboard_dist(bundled_dist, "v4.24.4")

    with mock.patch(
        "astrbot.core.dashboard_assets._get_bundled_dist_path",
        return_value=bundled_dist,
    ):
        assert _should_use_bundled_dist(user_dist, "v4.24.4") is True


def test_should_use_bundled_dashboard_dist_when_version_file_is_malformed(tmp_path):
    user_dist = tmp_path / "user-dist"
    bundled_dist = tmp_path / "bundled-dist"
    (user_dist / "assets").mkdir(parents=True)
    (bundled_dist / "assets").mkdir(parents=True)
    (user_dist / "assets" / "version").write_text("not-a-version", encoding="utf-8")
    _write_dashboard_dist(bundled_dist, "v4.24.4")

    with mock.patch(
        "astrbot.core.dashboard_assets._get_bundled_dist_path",
        return_value=bundled_dist,
    ):
        assert _should_use_bundled_dist(user_dist, "4.24.4") is True


def test_should_use_bundled_dashboard_dist_when_data_version_file_is_missing(tmp_path):
    user_dist = tmp_path / "user-dist"
    bundled_dist = tmp_path / "bundled-dist"
    (user_dist / "assets").mkdir(parents=True)
    _write_dashboard_dist(bundled_dist, "v4.24.4")

    with mock.patch(
        "astrbot.core.dashboard_assets._get_bundled_dist_path",
        return_value=bundled_dist,
    ):
        assert _should_use_bundled_dist(user_dist, "4.24.4") is True


def test_should_use_bundled_dashboard_dist_when_data_entries_are_incomplete(tmp_path):
    user_dist = tmp_path / "user-dist"
    bundled_dist = tmp_path / "bundled-dist"
    _write_dashboard_dist(user_dist, "v4.24.4")
    (user_dist / "assets" / "app.js").unlink()
    _write_dashboard_dist(bundled_dist, "v4.24.4")

    with mock.patch(
        "astrbot.core.dashboard_assets._get_bundled_dist_path",
        return_value=bundled_dist,
    ):
        assert _should_use_bundled_dist(user_dist, "4.24.4") is True


@pytest.mark.asyncio
async def test_get_dashboard_version_uses_bundled_dist_when_data_dist_is_missing(
    tmp_path,
):
    """Tests bundled WebUI version lookup when data/dist is absent."""
    from astrbot.core.config.default import VERSION

    data_dir = tmp_path / "data"
    bundled_dist = tmp_path / "bundled-dist"
    _write_dashboard_dist(bundled_dist, f"v{VERSION}")

    with mock.patch(
        "astrbot.core.dashboard_assets.get_astrbot_data_path",
        return_value=str(data_dir),
    ):
        with mock.patch(
            "astrbot.core.dashboard_assets._get_bundled_dist_path",
            return_value=bundled_dist,
        ):
            assert await get_dashboard_version() == f"v{VERSION}"


@pytest.mark.asyncio
async def test_check_dashboard_files_with_non_desktop_custom_webui_dir(
    monkeypatch, tmp_path
):
    """A custom explicit WebUI remains unchanged outside Desktop."""
    monkeypatch.delenv("ASTRBOT_DESKTOP_MANAGED", raising=False)
    valid_dir = tmp_path / "my-custom-webui"
    (valid_dir / "assets").mkdir(parents=True)
    (valid_dir / "index.html").write_text("custom", encoding="utf-8")
    updater = mock.Mock()
    monkeypatch.setattr("main.AstrBotUpdater", updater)

    result = await check_dashboard_files(webui_dir=str(valid_dir))

    assert result == str(valid_dir.absolute())
    updater.assert_not_called()


@pytest.mark.asyncio
async def test_check_dashboard_files_repairs_stale_desktop_webui(monkeypatch, tmp_path):
    """Desktop startup verifies the repaired dist before serving it."""
    monkeypatch.setenv("ASTRBOT_DESKTOP_MANAGED", "1")
    explicit_dist = tmp_path / "webui"
    (explicit_dist / "assets").mkdir(parents=True)
    (explicit_dist / "index.html").write_text("stale", encoding="utf-8")
    (explicit_dist / "assets" / "version").write_text("v0.0.1", encoding="utf-8")
    data_dir = tmp_path / "data"
    repaired_dist = data_dir / "dist"
    monkeypatch.setattr(
        "astrbot.core.dashboard_assets.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.dashboard_assets._get_bundled_dist_path",
        lambda: tmp_path / "missing-bundled-dist",
    )

    async def repair_dashboard():
        from astrbot.core.config.default import VERSION

        _write_dashboard_dist(repaired_dist, f"v{VERSION}")
        return repaired_dist

    ensure_dashboard = mock.AsyncMock(side_effect=repair_dashboard)
    monkeypatch.setattr(
        "main.AstrBotUpdater",
        lambda: mock.Mock(ensure_dashboard=ensure_dashboard),
    )

    result = await check_dashboard_files(str(explicit_dist))

    assert result == str(repaired_dist.absolute())
    ensure_dashboard.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failed_version",
    ["v0.0.2", None],
    ids=["known-stale", "unversioned"],
)
async def test_check_dashboard_files_does_not_serve_stale_desktop_webui_when_repair_fails(
    monkeypatch, tmp_path, failed_version
):
    """A failed desktop repair cannot fall back to unverified managed assets."""
    monkeypatch.setenv("ASTRBOT_DESKTOP_MANAGED", "1")
    explicit_dist = tmp_path / "webui"
    (explicit_dist / "assets").mkdir(parents=True)
    (explicit_dist / "index.html").write_text("stale", encoding="utf-8")
    (explicit_dist / "assets" / "version").write_text("v0.0.1", encoding="utf-8")
    data_dir = tmp_path / "data"
    failed_repair_dist = data_dir / "dist"
    (failed_repair_dist / "assets").mkdir(parents=True)
    (failed_repair_dist / "index.html").write_text("also stale", encoding="utf-8")
    if failed_version is not None:
        (failed_repair_dist / "assets" / "version").write_text(
            failed_version, encoding="utf-8"
        )
    monkeypatch.setattr(
        "astrbot.core.dashboard_assets.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.dashboard_assets._get_bundled_dist_path",
        lambda: tmp_path / "missing-bundled-dist",
    )
    # ensure_dashboard historically returns a usable stale dist when its download
    # fails. Startup must validate that fallback rather than trusting the path.
    ensure_dashboard = mock.AsyncMock(return_value=failed_repair_dist)
    monkeypatch.setattr(
        "main.AstrBotUpdater",
        lambda: mock.Mock(ensure_dashboard=ensure_dashboard),
    )

    assert await check_dashboard_files(str(explicit_dist)) is None
    assert resolve_dashboard_dist(str(explicit_dist)) is None
    ensure_dashboard.assert_awaited_once_with()
