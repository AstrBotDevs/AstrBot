"""Tests for resolve_dashboard_dist() when an explicit WebUI directory is used."""

from unittest.mock import patch

import pytest

from astrbot.core.config.default import VERSION
from astrbot.core.dashboard_assets import resolve_dashboard_dist

WARNING_FRAGMENT = "does not declare a version matching core"


def _make_dist(root, version: str | None) -> str:
    assets = root / "assets"
    assets.mkdir(parents=True)
    (root / "index.html").write_text("<html></html>", encoding="utf-8")
    if version is not None:
        (assets / "version").write_text(version, encoding="utf-8")
    return str(root)


class TestExplicitWebuiDir:
    def test_matching_version_is_served_quietly(self, tmp_path):
        """The happy path must not add startup noise."""
        dist = _make_dist(tmp_path / "webui", f"v{VERSION}")

        with patch("astrbot.core.dashboard_assets.logger.warning") as warning:
            resolved = resolve_dashboard_dist(dist)

        assert resolved is not None
        assert str(resolved) == str(tmp_path / "webui")
        warning.assert_not_called()

    def test_mismatched_version_warns_but_is_still_served(self, tmp_path):
        """A stale packaged WebUI must not be swapped in silently."""
        dist = _make_dist(tmp_path / "webui", "v0.0.1")

        with patch("astrbot.core.dashboard_assets.logger.warning") as warning:
            resolved = resolve_dashboard_dist(dist)

        assert resolved is not None  # behaviour unchanged: still served
        warning.assert_called_once()
        message, actual_version, expected_version, _ = warning.call_args.args
        assert WARNING_FRAGMENT in message
        assert actual_version == "v0.0.1"
        assert expected_version == VERSION

    def test_missing_version_marker_warns_as_unknown(self, tmp_path):
        """Assets without a version marker cannot be verified, so say so."""
        dist = _make_dist(tmp_path / "webui", None)

        with patch("astrbot.core.dashboard_assets.logger.warning") as warning:
            resolved = resolve_dashboard_dist(dist)

        assert resolved is not None
        warning.assert_called_once()
        _, actual_version, expected_version, _ = warning.call_args.args
        assert actual_version == "unknown"
        assert expected_version == VERSION

    def test_nonexistent_explicit_dir_is_rejected(self, tmp_path):
        """An explicit missing path must fail instead of hiding a typo."""
        with pytest.raises(ValueError, match="must contain index.html"):
            resolve_dashboard_dist(str(tmp_path / "does-not-exist"))

    def test_explicit_regular_file_is_rejected(self, tmp_path):
        """A regular file cannot be used as a Dashboard directory."""
        path = tmp_path / "index.html"
        path.write_text("<html></html>", encoding="utf-8")
        with pytest.raises(ValueError, match="must contain index.html"):
            resolve_dashboard_dist(path)

    @pytest.mark.parametrize("empty", ["", None])
    def test_no_explicit_dir_falls_through(self, empty):
        """Without --webui-dir the managed/bundled resolution path is used."""
        with patch("astrbot.core.dashboard_assets.logger.warning") as warning:
            resolve_dashboard_dist(empty)

        warning.assert_not_called()
