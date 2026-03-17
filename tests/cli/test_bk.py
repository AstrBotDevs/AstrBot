import asyncio
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from astrbot.cli.commands.cmd_bk import bk
from astrbot.core.backup.importer import ImportResult


@pytest.fixture
def mock_exporter():
    with patch("astrbot.cli.commands.cmd_bk.AstrBotExporter") as mock:
        exporter_instance = mock.return_value
        # export_all is async, return a fake path string
        exporter_instance.export_all = AsyncMock(return_value="fake_backup.zip")
        yield exporter_instance


@pytest.fixture
def mock_importer():
    with patch("astrbot.cli.commands.cmd_bk.AstrBotImporter") as mock:
        importer_instance = mock.return_value
        # import_all is async
        result = ImportResult()
        importer_instance.import_all = AsyncMock(return_value=result)
        yield importer_instance


@pytest.fixture
def mock_kb_manager():
    with patch(
        "astrbot.cli.commands.cmd_bk._get_kb_manager", new_callable=AsyncMock
    ) as mock:
        mock.return_value = MagicMock()
        yield mock


@pytest.fixture
def mock_gpg_tools():
    """Mock shutil.which and asyncio.create_subprocess_exec for GPG operations"""
    # Create a mock process object
    mock_process = MagicMock()
    mock_process.wait = AsyncMock(return_value=None)
    mock_process.returncode = 0

    with patch("astrbot.cli.commands.cmd_bk.shutil.which") as mock_which, patch(
        "asyncio.create_subprocess_exec", new_callable=AsyncMock
    ) as mock_exec:
        mock_which.return_value = "/usr/bin/gpg"
        mock_exec.return_value = mock_process
        yield mock_which, mock_exec


def test_export_simple(mock_exporter, mock_kb_manager):
    """Test basic export command"""
    runner = CliRunner()
    result = runner.invoke(bk, ["export"])

    assert result.exit_code == 0
    assert "Raw backup exported to: fake_backup.zip" in result.output
    mock_exporter.export_all.assert_called_once()


def test_export_custom_output(mock_exporter, mock_kb_manager):
    """Test export with output directory"""
    runner = CliRunner()
    result = runner.invoke(bk, ["export", "-o", "/tmp/backups"])

    assert result.exit_code == 0
    mock_exporter.export_all.assert_called_once()
    assert mock_exporter.export_all.call_args[0][0] == "/tmp/backups"


def test_export_gpg_sign(mock_exporter, mock_kb_manager, mock_gpg_tools):
    """Test export with GPG signing"""
    _, mock_exec = mock_gpg_tools
    runner = CliRunner()

    # Mock Path operations used in GPG block
    with patch("pathlib.Path.unlink") as mock_unlink, patch(
        "pathlib.Path.exists", return_value=True
    ):

        result = runner.invoke(bk, ["export", "--gpg-sign"])

        assert result.exit_code == 0
        mock_exec.assert_called()
        # create_subprocess_exec(*cmd) -> args are the command parts as separate args
        args = mock_exec.call_args[0]
        # Verify GPG command construction
        assert args[0] == "gpg"
        assert "--sign" in args
        assert "--yes" in args
        # Should clean up original file
        mock_unlink.assert_called()


def test_export_gpg_encrypt(mock_exporter, mock_kb_manager, mock_gpg_tools):
    """Test export with GPG asymmetric encryption"""
    _, mock_exec = mock_gpg_tools
    runner = CliRunner()

    with patch("pathlib.Path.unlink"), patch("pathlib.Path.exists", return_value=True):
        result = runner.invoke(bk, ["export", "--gpg-encrypt", "user@example.com"])

        assert result.exit_code == 0
        args = mock_exec.call_args[0]
        assert "--encrypt" in args
        assert "--recipient" in args
        assert "user@example.com" in args


def test_export_gpg_symmetric(mock_exporter, mock_kb_manager, mock_gpg_tools):
    """Test export with GPG symmetric encryption"""
    _, mock_exec = mock_gpg_tools
    runner = CliRunner()

    with patch("pathlib.Path.unlink"), patch("pathlib.Path.exists", return_value=True):
        result = runner.invoke(bk, ["export", "--gpg-symmetric"])

        assert result.exit_code == 0
        args = mock_exec.call_args[0]
        assert "--symmetric" in args
        assert "--yes" in args


def test_export_digest(mock_exporter, mock_kb_manager):
    """Test export with digest generation"""
    runner = CliRunner()

    # Mock file operations for digest calculation
    mock_data = b"test data for checksum"
    with patch("builtins.open", new_callable=MagicMock) as mock_open, patch(
        "pathlib.Path.write_text"
    ) as mock_write_text:

        # Mock reading file content
        file_handle = mock_open.return_value.__enter__.return_value
        file_handle.read.side_effect = [mock_data, b""]  # Data then EOF

        result = runner.invoke(bk, ["export", "--digest", "sha256"])

        assert result.exit_code == 0
        assert "Digest generated" in result.output

        # Verify hash calculation
        expected_hash = hashlib.sha256(mock_data).hexdigest()
        mock_write_text.assert_called_once()
        content = mock_write_text.call_args[0][0]
        assert expected_hash in content
        assert "fake_backup.zip" in content


def test_import_simple(mock_importer, mock_kb_manager):
    """Test basic import command"""
    runner = CliRunner()

    with patch("pathlib.Path.exists", return_value=True):
        result = runner.invoke(bk, ["import", "backup.zip", "--yes"])

        assert result.exit_code == 0
        assert "Import completed successfully" in result.output
        mock_importer.import_all.assert_called_once()


def test_import_decrypt(mock_importer, mock_kb_manager, mock_gpg_tools):
    """Test import with GPG decryption"""
    _, mock_exec = mock_gpg_tools
    runner = CliRunner()

    # path.exists needs to return True for initial check,
    # then unlink needs to be mocked for cleanup
    with patch("pathlib.Path.exists", return_value=True), patch(
        "pathlib.Path.unlink"
    ) as mock_unlink:

        result = runner.invoke(bk, ["import", "backup.zip.gpg", "--yes"])

        assert result.exit_code == 0
        assert "Processing GPG file" in result.output

        # Verify GPG decryption call
        mock_exec.assert_called()
        args = mock_exec.call_args[0]
        assert args[0] == "gpg"
        assert "--decrypt" in args
        assert "backup.zip.gpg" in str(args[-1])

        # Verify temp file cleanup
        mock_unlink.assert_called()


def test_import_abort(mock_importer):
    """Test import abort on confirmation decline"""
    runner = CliRunner()
    with patch("pathlib.Path.exists", return_value=True):
        result = runner.invoke(bk, ["import", "backup.zip"], input="n\n")

        assert result.exit_code != 0
        assert "Aborted" in result.output
        mock_importer.import_all.assert_not_called()


def test_export_gpg_missing(mock_exporter, mock_kb_manager):
    """Test error when GPG is missing"""
    with patch("astrbot.cli.commands.cmd_bk.shutil.which", return_value=None):
        runner = CliRunner()
        result = runner.invoke(bk, ["export", "--gpg-sign"])

        assert result.exit_code != 0
        assert "GPG tool not found" in result.output


def test_export_gpg_recipient_recovery(mock_exporter, mock_kb_manager, mock_gpg_tools):
    """Test recovery when -E consumes a flag"""
    _, mock_exec = mock_gpg_tools
    runner = CliRunner()

    with patch("pathlib.Path.unlink"), patch("pathlib.Path.exists", return_value=True):
        # input="user@example.com\n" provides the recipient when prompted
        result = runner.invoke(bk, ["export", "-E", "-S"], input="user@example.com\n")

        assert result.exit_code == 0
        assert "Warning: Flag '-S' was interpreted as the recipient" in result.output
        assert "Recovered flag -S (Sign)" in result.output

        # Verify GPG command has both sign and encrypt with correct recipient
        args = mock_exec.call_args[0]
        assert "--sign" in args
        assert "--encrypt" in args
        assert "user@example.com" in args
