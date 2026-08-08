import logging
import os
import sys
from pathlib import Path

# 将项目根目录添加到 sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest import mock

import pytest

from astrbot.application import prepare_runtime_environment, resolve_dashboard_assets
from astrbot.core.utils.io import (
    get_dashboard_version,
    should_use_bundled_dashboard_dist,
)
from main import (
    DASHBOARD_RESET_PASSWORD_ENV,
    _apply_startup_env_flags,
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


def test_prepare_runtime_environment(monkeypatch):
    version_info_correct = _version_info(3, 14)
    version_info_wrong = _version_info(3, 13)
    monkeypatch.setattr(sys, "version_info", version_info_correct)
    with mock.patch("os.makedirs") as mock_makedirs:
        prepare_runtime_environment()
        # prepare_runtime_environment uses get_astrbot_*_path() which returns absolute paths,
        # so just verify makedirs was called the expected number of times
        assert mock_makedirs.call_count >= 4
        # Verify all calls used exist_ok=True
        for call_args in mock_makedirs.call_args_list:
            assert call_args[1].get("exist_ok") is True

    monkeypatch.setattr(sys, "version_info", version_info_wrong)
    with pytest.raises(SystemExit):
        prepare_runtime_environment()


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


def test_prepare_runtime_environment_appends_user_site_packages_after_runtime_paths(monkeypatch):
    astrbot_root = "/tmp/astrbot-root"
    site_packages_path = "/tmp/astrbot-site-packages"
    original_sys_path = list(sys.path)

    monkeypatch.setattr(sys, "version_info", _version_info(3, 14))
    monkeypatch.setattr("astrbot.application.get_astrbot_root", lambda: astrbot_root)
    monkeypatch.setattr(
        "astrbot.application.get_astrbot_site_packages_path", lambda: site_packages_path
    )
    monkeypatch.setattr("astrbot.application.get_astrbot_config_path", lambda: "/tmp/config")
    monkeypatch.setattr("astrbot.application.get_astrbot_plugin_path", lambda: "/tmp/plugins")
    monkeypatch.setattr("astrbot.application.get_astrbot_temp_path", lambda: "/tmp/temp")
    monkeypatch.setattr("astrbot.application.get_astrbot_knowledge_base_path", lambda: "/tmp/kb")
    monkeypatch.setattr(sys, "path", ["/runtime/lib", *original_sys_path])

    with mock.patch("os.makedirs"):
        prepare_runtime_environment()

    assert sys.path[0] == astrbot_root
    assert sys.path[-1] == site_packages_path
    assert sys.path.index(site_packages_path) > sys.path.index("/runtime/lib")


def test_prepare_runtime_environment_does_not_append_duplicate_user_site_packages(monkeypatch):
    astrbot_root = "/tmp/astrbot-root"
    site_packages_path = "/tmp/astrbot-site-packages"
    original_sys_path = list(sys.path)

    monkeypatch.setattr(sys, "version_info", _version_info(3, 14))
    monkeypatch.setattr("astrbot.application.get_astrbot_root", lambda: astrbot_root)
    monkeypatch.setattr(
        "astrbot.application.get_astrbot_site_packages_path", lambda: site_packages_path
    )
    monkeypatch.setattr("astrbot.application.get_astrbot_config_path", lambda: "/tmp/config")
    monkeypatch.setattr("astrbot.application.get_astrbot_plugin_path", lambda: "/tmp/plugins")
    monkeypatch.setattr("astrbot.application.get_astrbot_temp_path", lambda: "/tmp/temp")
    monkeypatch.setattr("astrbot.application.get_astrbot_knowledge_base_path", lambda: "/tmp/kb")
    monkeypatch.setattr(
        sys, "path", [astrbot_root, *original_sys_path, site_packages_path]
    )

    with mock.patch("os.makedirs"):
        prepare_runtime_environment()

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
async def test_resolve_dashboard_assets_not_exists(tmp_path):
    """Tests startup disables WebUI when no local build exists."""
    data_dir = tmp_path / "data"
    bundled_dist = tmp_path / "bundled-dist"

    with mock.patch("astrbot.application.get_astrbot_data_path", return_value=str(data_dir)):
        with mock.patch(
            "astrbot.application.get_repo_dashboard_dist_path",
            return_value=tmp_path / "repo-dist",
        ):
            with mock.patch(
                "astrbot.application.get_bundled_dashboard_dist_path",
                return_value=bundled_dist,
            ):
                result = await resolve_dashboard_assets()

    assert result is None


@pytest.mark.asyncio
async def test_resolve_dashboard_assets_uses_bundled_dist_without_download(tmp_path):
    """Tests that bundled dashboard assets are used when data/dist is absent."""
    from astrbot.application import VERSION

    data_dir = tmp_path / "data"
    bundled_dist = tmp_path / "bundled-dist"
    (bundled_dist / "assets").mkdir(parents=True)
    (bundled_dist / "assets" / "version").write_text(f"v{VERSION}", encoding="utf-8")
    (bundled_dist / "index.html").write_text("bundled", encoding="utf-8")

    with mock.patch("astrbot.application.get_astrbot_data_path", return_value=str(data_dir)):
        with mock.patch(
            "astrbot.application.get_repo_dashboard_dist_path",
            return_value=tmp_path / "repo-dist",
        ):
            with mock.patch(
                "astrbot.application.get_bundled_dashboard_dist_path",
                return_value=bundled_dist,
            ):
                result = await resolve_dashboard_assets()

    assert result == str(bundled_dist)


@pytest.mark.asyncio
async def test_resolve_dashboard_assets_exists_and_version_match(tmp_path):
    """Tests that dashboard is not downloaded when it exists and version matches."""
    from astrbot.application import VERSION

    data_dir = tmp_path / "data"
    data_dist = data_dir / "dist"
    (data_dist / "assets").mkdir(parents=True)
    (data_dist / "assets" / "version").write_text(f"v{VERSION}", encoding="utf-8")
    (data_dist / "index.html").write_text("user", encoding="utf-8")

    with mock.patch("astrbot.application.get_astrbot_data_path", return_value=str(data_dir)):
        with mock.patch(
            "astrbot.application.get_repo_dashboard_dist_path",
            return_value=tmp_path / "repo-dist",
        ):
            result = await resolve_dashboard_assets()
            assert result == str(data_dist)


@pytest.mark.asyncio
async def test_resolve_dashboard_assets_rejects_version_mismatch(tmp_path):
    """Tests that startup rejects a mismatched local dashboard."""
    data_dir = tmp_path / "data"
    data_dist = data_dir / "dist"
    bundled_dist = tmp_path / "bundled-dist"
    (data_dist / "assets").mkdir(parents=True)
    (data_dist / "assets" / "version").write_text("v0.0.1", encoding="utf-8")

    with mock.patch("astrbot.application.get_astrbot_data_path", return_value=str(data_dir)):
        with mock.patch(
            "astrbot.application.get_repo_dashboard_dist_path",
            return_value=tmp_path / "repo-dist",
        ):
            with mock.patch(
                "astrbot.application.get_bundled_dashboard_dist_path",
                return_value=bundled_dist,
            ):
                with mock.patch("astrbot.application.logger.warning") as mock_logger_warning:
                    result = await resolve_dashboard_assets()

    assert result is None
    assert any(
        "Ignoring incompatible data/dist WebUI" in call.args[0]
        for call in mock_logger_warning.call_args_list
    )


@pytest.mark.asyncio
async def test_resolve_dashboard_assets_rejects_incomplete_matching_dist(
    tmp_path,
):
    """Tests that a version match alone is not enough to serve WebUI."""
    from astrbot.application import VERSION

    data_dir = tmp_path / "data"
    data_dist = data_dir / "dist"
    bundled_dist = tmp_path / "bundled-dist"
    (data_dist / "assets").mkdir(parents=True)
    (data_dist / "assets" / "version").write_text(f"v{VERSION}", encoding="utf-8")

    with mock.patch("astrbot.application.get_astrbot_data_path", return_value=str(data_dir)):
        with mock.patch(
            "astrbot.application.get_repo_dashboard_dist_path",
            return_value=tmp_path / "repo-dist",
        ):
            with mock.patch(
                "astrbot.application.get_bundled_dashboard_dist_path",
                return_value=bundled_dist,
            ):
                result = await resolve_dashboard_assets()

    assert result is None


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
    from astrbot.application import VERSION

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
            "astrbot.core.utils.io.get_repo_dashboard_dist_path",
            return_value=tmp_path / "repo-dist",
        ):
            with mock.patch(
                "astrbot.core.utils.io.get_bundled_dashboard_dist_path",
                return_value=bundled_dist,
            ):
                assert await get_dashboard_version() == f"v{VERSION}"


@pytest.mark.asyncio
async def test_get_dashboard_version_uses_repo_dist_when_data_dist_is_missing(
    tmp_path,
):
    """Tests source-tree WebUI version lookup when data/dist is absent."""
    from astrbot.application import VERSION

    data_dir = tmp_path / "data"
    repo_dist = tmp_path / "repo-dist"
    bundled_dist = tmp_path / "bundled-dist"
    (repo_dist / "assets").mkdir(parents=True)
    (repo_dist / "assets" / "version").write_text(f"v{VERSION}", encoding="utf-8")
    (repo_dist / "index.html").write_text("repo", encoding="utf-8")

    with mock.patch(
        "astrbot.core.utils.io.get_astrbot_data_path",
        return_value=str(data_dir),
    ):
        with mock.patch(
            "astrbot.core.utils.io.get_repo_dashboard_dist_path",
            return_value=repo_dist,
        ):
            with mock.patch(
                "astrbot.core.utils.io.get_bundled_dashboard_dist_path",
                return_value=bundled_dist,
            ):
                assert await get_dashboard_version() == f"v{VERSION}"


@pytest.mark.asyncio
async def test_get_dashboard_version_prefers_repo_dist_when_data_dist_is_stale(
    tmp_path,
):
    """Tests source-tree WebUI is preferred over stale data/dist."""
    from astrbot.application import VERSION

    data_dir = tmp_path / "data"
    data_dist = data_dir / "dist"
    repo_dist = tmp_path / "repo-dist"
    bundled_dist = tmp_path / "bundled-dist"
    (data_dist / "assets").mkdir(parents=True)
    (repo_dist / "assets").mkdir(parents=True)
    (data_dist / "assets" / "version").write_text("v0.0.1", encoding="utf-8")
    (data_dist / "index.html").write_text("stale", encoding="utf-8")
    (repo_dist / "assets" / "version").write_text(f"v{VERSION}", encoding="utf-8")
    (repo_dist / "index.html").write_text("repo", encoding="utf-8")

    with mock.patch(
        "astrbot.core.utils.io.get_astrbot_data_path",
        return_value=str(data_dir),
    ):
        with mock.patch(
            "astrbot.core.utils.io.get_repo_dashboard_dist_path",
            return_value=repo_dist,
        ):
            with mock.patch(
                "astrbot.core.utils.io.get_bundled_dashboard_dist_path",
                return_value=bundled_dist,
            ):
                assert await get_dashboard_version() == f"v{VERSION}"


@pytest.mark.asyncio
async def test_resolve_dashboard_assets_replaces_stale_data_dist_with_bundled_dist(
    tmp_path,
):
    """Tests that a stale data/dist is repaired from bundled dashboard assets."""
    from astrbot.application import VERSION

    data_dir = tmp_path / "data"
    data_dist = data_dir / "dist"
    bundled_dist = tmp_path / "bundled-dist"
    (data_dist / "assets").mkdir(parents=True)
    (bundled_dist / "assets").mkdir(parents=True)
    (data_dist / "assets" / "version").write_text("v0.0.1", encoding="utf-8")
    (data_dist / "old.txt").write_text("old", encoding="utf-8")
    (bundled_dist / "assets" / "version").write_text(f"v{VERSION}", encoding="utf-8")
    (bundled_dist / "index.html").write_text("bundled", encoding="utf-8")

    with mock.patch("astrbot.application.get_astrbot_data_path", return_value=str(data_dir)):
        with mock.patch(
            "astrbot.application.get_repo_dashboard_dist_path",
            return_value=tmp_path / "repo-dist",
        ):
            with mock.patch(
                "astrbot.application.get_bundled_dashboard_dist_path",
                return_value=Path(bundled_dist),
            ):
                with mock.patch(
                    "astrbot.core.utils.io.get_bundled_dashboard_dist_path",
                    return_value=Path(bundled_dist),
                ):
                    result = await resolve_dashboard_assets()

    assert result == str(data_dist)
    assert (data_dist / "assets" / "version").read_text(
        encoding="utf-8"
    ) == f"v{VERSION}"
    assert (data_dist / "index.html").read_text(encoding="utf-8") == "bundled"
    assert not (data_dist / "old.txt").exists()


@pytest.mark.asyncio
async def test_resolve_dashboard_assets_uses_repo_dist_when_data_dist_is_missing(
    tmp_path,
):
    """Tests startup prefers source-tree WebUI before downloading."""
    from astrbot.application import VERSION

    data_dir = tmp_path / "data"
    repo_dist = tmp_path / "repo-dist"
    bundled_dist = tmp_path / "bundled-dist"
    (repo_dist / "assets").mkdir(parents=True)
    (repo_dist / "assets" / "version").write_text(f"v{VERSION}", encoding="utf-8")
    (repo_dist / "index.html").write_text("repo", encoding="utf-8")

    with mock.patch("astrbot.application.get_astrbot_data_path", return_value=str(data_dir)):
        with mock.patch(
            "astrbot.application.get_repo_dashboard_dist_path",
            return_value=repo_dist,
        ):
            with mock.patch(
                "astrbot.application.get_bundled_dashboard_dist_path",
                return_value=bundled_dist,
            ):
                result = await resolve_dashboard_assets()

    assert result == str(repo_dist)


@pytest.mark.asyncio
async def test_resolve_dashboard_assets_uses_repo_dist_when_data_dist_is_stale(
    tmp_path,
):
    """Tests startup prefers source-tree WebUI over stale data/dist."""
    from astrbot.application import VERSION

    data_dir = tmp_path / "data"
    data_dist = data_dir / "dist"
    repo_dist = tmp_path / "repo-dist"
    bundled_dist = tmp_path / "bundled-dist"
    (data_dist / "assets").mkdir(parents=True)
    (repo_dist / "assets").mkdir(parents=True)
    (data_dist / "assets" / "version").write_text("v0.0.1", encoding="utf-8")
    (data_dist / "index.html").write_text("stale", encoding="utf-8")
    (repo_dist / "assets" / "version").write_text(f"v{VERSION}", encoding="utf-8")
    (repo_dist / "index.html").write_text("repo", encoding="utf-8")

    with mock.patch("astrbot.application.get_astrbot_data_path", return_value=str(data_dir)):
        with mock.patch(
            "astrbot.application.get_repo_dashboard_dist_path",
            return_value=repo_dist,
        ):
            with mock.patch(
                "astrbot.application.get_bundled_dashboard_dist_path",
                return_value=bundled_dist,
            ):
                result = await resolve_dashboard_assets()

    assert result == str(repo_dist)


@pytest.mark.asyncio
async def test_resolve_dashboard_assets_prefers_repo_dist_when_data_dist_matches(
    tmp_path,
):
    """Tests startup prefers source-tree WebUI over data/dist in source checkout."""
    from astrbot.application import VERSION

    data_dir = tmp_path / "data"
    data_dist = data_dir / "dist"
    repo_dist = tmp_path / "repo-dist"
    bundled_dist = tmp_path / "bundled-dist"
    (data_dist / "assets").mkdir(parents=True)
    (repo_dist / "assets").mkdir(parents=True)
    (data_dist / "assets" / "version").write_text(f"v{VERSION}", encoding="utf-8")
    (data_dist / "index.html").write_text("user", encoding="utf-8")
    (repo_dist / "assets" / "version").write_text(f"v{VERSION}", encoding="utf-8")
    (repo_dist / "index.html").write_text("repo", encoding="utf-8")

    with mock.patch("astrbot.application.get_astrbot_data_path", return_value=str(data_dir)):
        with mock.patch(
            "astrbot.application.get_repo_dashboard_dist_path",
            return_value=repo_dist,
        ):
            with mock.patch(
                "astrbot.application.get_bundled_dashboard_dist_path",
                return_value=bundled_dist,
            ):
                result = await resolve_dashboard_assets()

    assert result == str(repo_dist)


def _make_explicit_dashboard_dist(tmp_path, version: str | None):
    """Create a minimal explicitly selected Dashboard directory."""
    dist = tmp_path / "explicit-webui"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    if version is not None:
        (dist / "assets" / "version").write_text(version, encoding="utf-8")
    return dist


@pytest.mark.asyncio
async def test_resolve_dashboard_assets_uses_matching_explicit_webui_dir(
    tmp_path,
    caplog,
):
    """An explicitly selected matching build remains the administrator's choice."""
    from astrbot.application import VERSION

    explicit_dist = _make_explicit_dashboard_dist(tmp_path, f"v{VERSION}")

    with caplog.at_level(logging.WARNING):
        result = await resolve_dashboard_assets(webui_dir=str(explicit_dist))

    assert result == str(explicit_dist)
    assert "does not declare a version matching core" not in caplog.text


@pytest.mark.asyncio
async def test_resolve_dashboard_assets_warns_for_mismatched_explicit_webui_dir(
    tmp_path,
    caplog,
):
    """An explicit stale build is served with an actionable compatibility warning."""
    explicit_dist = _make_explicit_dashboard_dist(tmp_path, "v0.0.1")

    with caplog.at_level(logging.WARNING):
        result = await resolve_dashboard_assets(webui_dir=str(explicit_dist))

    assert result == str(explicit_dist)
    assert "does not declare a version matching core" in caplog.text
    assert "v0.0.1" in caplog.text


@pytest.mark.asyncio
async def test_resolve_dashboard_assets_warns_for_explicit_webui_without_marker(
    tmp_path,
    caplog,
):
    """A marker-less explicit build is served but cannot be silently verified."""
    explicit_dist = _make_explicit_dashboard_dist(tmp_path, None)

    with caplog.at_level(logging.WARNING):
        result = await resolve_dashboard_assets(webui_dir=str(explicit_dist))

    assert result == str(explicit_dist)
    assert "does not declare a version matching core" in caplog.text
    assert "unknown" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("webui_dir", ["", None])
async def test_resolve_dashboard_assets_empty_explicit_dir_has_no_stale_warning(
    webui_dir,
    caplog,
):
    """An absent option must keep ordinary resolution behavior unchanged."""
    with caplog.at_level(logging.WARNING):
        await resolve_dashboard_assets(webui_dir=webui_dir)

    assert "does not declare a version matching core" not in caplog.text


@pytest.mark.asyncio
async def test_resolve_dashboard_assets_missing_explicit_dir_has_no_stale_warning(
    tmp_path,
    caplog,
):
    """A nonexistent option falls through instead of being labelled stale."""
    with caplog.at_level(logging.WARNING):
        await resolve_dashboard_assets(webui_dir=str(tmp_path / "missing"))

    assert "does not declare a version matching core" not in caplog.text
