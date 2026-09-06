"""Comprehensive tests for CLI utilities."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path

from astrbot.cli.utils.version_comparator import VersionComparator


class TestVersionComparator:
    """Tests for version comparison utilities."""

    def test_compare_versions_equal(self):
        """Test comparing equal versions."""
        assert VersionComparator.compare_version("1.0.0", "1.0.0") == 0

    def test_compare_versions_greater(self):
        """Test comparing greater version."""
        assert VersionComparator.compare_version("2.0.0", "1.0.0") > 0

    def test_compare_versions_less(self):
        """Test comparing lesser version."""
        assert VersionComparator.compare_version("1.0.0", "2.0.0") < 0

    def test_compare_versions_with_patch(self):
        """Test comparing versions with patch numbers."""
        assert VersionComparator.compare_version("1.0.1", "1.0.0") > 0
        assert VersionComparator.compare_version("1.0.0", "1.0.1") < 0

    def test_compare_versions_with_prerelease(self):
        """Test comparing versions with prerelease."""
        assert VersionComparator.compare_version("1.0.0-alpha", "1.0.0") < 0
        assert VersionComparator.compare_version("1.0.0-beta", "1.0.0-alpha") > 0

    def test_compare_versions_with_v_prefix(self):
        """Test comparing versions with v prefix."""
        assert VersionComparator.compare_version("v1.0.0", "v1.0.0") == 0
        assert VersionComparator.compare_version("v2.0.0", "v1.0.0") > 0

    def test_compare_versions_more_digits(self):
        """Test comparing versions with more than 3 digits."""
        assert VersionComparator.compare_version("1.0.0.1", "1.0.0.0") > 0
        assert VersionComparator.compare_version("1.0.0.0", "1.0.0.1") < 0

    def test_compare_versions_case_insensitive(self):
        """Test version comparison is case insensitive."""
        assert VersionComparator.compare_version("V1.0.0", "v1.0.0") == 0

    def test_split_prerelease_alpha(self):
        """Test splitting prerelease alpha."""
        result = VersionComparator._split_prerelease("alpha")
        assert result == ["alpha"]

    def test_split_prerelease_with_number(self):
        """Test splitting prerelease with number."""
        result = VersionComparator._split_prerelease("alpha.1")
        assert result == ["alpha", 1]

    def test_split_prerelease_multiple(self):
        """Test splitting multiple prerelease parts."""
        result = VersionComparator._split_prerelease("alpha.1.beta.2")
        assert result == ["alpha", 1, "beta", 2]

    def test_split_prerelease_none(self):
        """Test splitting None prerelease."""
        result = VersionComparator._split_prerelease(None)
        assert result is None


class TestDashboardManager:
    """Tests for DashboardManager."""

    @pytest.mark.asyncio
    async def test_ensure_installed_bundled(self):
        """Test dashboard installation when bundled."""
        from astrbot.cli.utils.dashboard import DashboardManager

        with patch.object(DashboardManager, '_bundled_dist', Path(__file__).parent):
            manager = DashboardManager()
            # Should not raise and should return early
            await manager.ensure_installed(Path("/tmp"))

    @pytest.mark.asyncio
    async def test_ensure_installed_no_bundled(self):
        """Test dashboard installation when not bundled."""
        from astrbot.cli.utils.dashboard import DashboardManager

        with patch.object(DashboardManager, '_bundled_dist', Path("/nonexistent")):
            with patch("os.environ.get", return_value="1"):  # systemd mode
                manager = DashboardManager()
                await manager.ensure_installed(Path("/tmp"))
                # Should skip in systemd mode
