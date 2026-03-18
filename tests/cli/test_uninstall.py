import platform
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from click.testing import CliRunner

from astrbot.cli.commands.cmd_uninstall import uninstall


@pytest.fixture
def mock_systemctl():
    """Mock shutil.which('systemctl') and subprocess.run"""
    with patch("astrbot.cli.commands.cmd_uninstall.shutil.which") as mock_which, patch(
        "astrbot.cli.commands.cmd_uninstall.subprocess.run"
    ) as mock_run:
        mock_which.return_value = "/usr/bin/systemctl"
        yield mock_which, mock_run


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


@pytest.mark.skipif(platform.system() != "Linux", reason="Systemd tests only on Linux")
def test_uninstall_systemd_service(mock_systemctl, mock_astrbot_paths):
    """Test systemd service removal"""
    mock_which, mock_run = mock_systemctl
    runner = CliRunner()

    # Mock Path.home() to return a temp directory
    with patch("pathlib.Path.home") as mock_home:
        fake_home = mock_astrbot_paths.root / "home"
        fake_home.mkdir()
        mock_home.return_value = fake_home

        # Create fake service file
        service_dir = fake_home / ".config" / "systemd" / "user"
        service_dir.mkdir(parents=True)
        service_file = service_dir / "astrbot.service"
        service_file.write_text("fake service content")

        # Run with --yes to skip confirmation, --keep-data to focus on systemd
        result = runner.invoke(uninstall, ["--yes", "--keep-data"])

        assert result.exit_code == 0
        assert "Stopping AstrBot service..." in result.output
        assert "Systemd service uninstalled." in result.output

        # Verify subprocess calls
        mock_run.assert_any_call(
            ["systemctl", "--user", "stop", "astrbot"], check=False
        )
        mock_run.assert_any_call(
            ["systemctl", "--user", "disable", "astrbot"], check=False
        )
        mock_run.assert_any_call(["systemctl", "--user", "daemon-reload"], check=True)

        # Verify file removed
        assert not service_file.exists()


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
    assert "AstrBot data removed successfully" in result.output

    # Verify removal
    assert not mock_astrbot_paths.data.exists()
    assert not (mock_astrbot_paths.root / ".astrbot").exists()
    assert not (mock_astrbot_paths.root / "astrbot.lock").exists()


def test_uninstall_keep_data(mock_astrbot_paths):
    """Test uninstall with --keep-data"""
    runner = CliRunner()

    result = runner.invoke(uninstall, ["--yes", "--keep-data"])

    assert result.exit_code == 0
    assert "Skipping data removal as requested" in result.output

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
