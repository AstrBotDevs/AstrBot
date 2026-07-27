import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from astrbot.cli.commands.cmd_uninstall import uninstall


@pytest.fixture
def mock_astrbot_paths(tmp_path):
    """Mock astrbot_paths to use a temporary directory"""
    with patch("astrbot.cli.commands.cmd_uninstall.astrbot_paths") as mock_paths:
        # Create a fake astrbot root structure in tmp_path
        root = tmp_path / "astrbot_root"
        root.mkdir()
        data = root / "data"
        data.mkdir()
        dot_astrbot = root / ".astrbot"
        dot_astrbot.touch()
        lock_file = root / "astrbot.lock"
        lock_file.touch()

        mock_paths.root = root
        mock_paths.data = data
        yield mock_paths


def test_uninstall_data_removal(mock_astrbot_paths):
    """Test data directory removal"""
    runner = CliRunner()

    # Verify pre-state
    assert mock_astrbot_paths.data.exists()
    assert (mock_astrbot_paths.root / ".astrbot").exists()
    assert (mock_astrbot_paths.root / "astrbot.lock").exists()

    # Run uninstall with --yes
    result = runner.invoke(uninstall, ["--yes"])

    assert result.exit_code == 0
    assert "AstrBot files removed successfully" in result.output

    # Verify removal
    assert not mock_astrbot_paths.data.exists()
    assert not (mock_astrbot_paths.root / ".astrbot").exists()
    assert not (mock_astrbot_paths.root / "astrbot.lock").exists()


def test_uninstall_keep_data(mock_astrbot_paths):
    """Test uninstall with --keep-data"""
    runner = CliRunner()

    result = runner.invoke(uninstall, ["--yes", "--keep-data"])

    assert result.exit_code == 0
    assert "Keeping data directory as requested" in result.output

    # Verify data still exists
    assert mock_astrbot_paths.data.exists()


def test_uninstall_abort_on_no_confirm(mock_astrbot_paths):
    """Test abort when user declines confirmation"""
    runner = CliRunner()

    # Input "n" to decline
    result = runner.invoke(uninstall, input="n\n")

    assert result.exit_code != 0
    assert "Aborted" in result.output

    # Verify data still exists
    assert mock_astrbot_paths.data.exists()


def test_uninstall_not_astrbot_root(mock_astrbot_paths):
    """Test running uninstall in a non-AstrBot directory"""
    # Remove the marker files
    shutil.rmtree(mock_astrbot_paths.data)
    (mock_astrbot_paths.root / ".astrbot").unlink()

    runner = CliRunner()
    result = runner.invoke(uninstall, ["--yes"])

    assert result.exit_code == 0
    assert "No AstrBot initialization found" in result.output
