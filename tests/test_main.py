import os
import sys

# 将项目根目录添加到 sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest import mock

import pytest

from main import check_dashboard_files, check_env


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
