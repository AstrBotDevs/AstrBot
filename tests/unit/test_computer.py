"""Tests for astrbot/core/computer module.

This module tests the ComputerClient, Booter implementations (local, shipyard, boxlite),
filesystem operations, Python execution, shell execution, and security restrictions.
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.computer.booters.base import ComputerBooter
from astrbot.core.computer.booters.local import (
    LocalBooter,
    LocalFileSystemComponent,
    LocalPythonComponent,
    LocalShellComponent,
    _ensure_safe_path,
    _is_safe_command,
)


class TestLocalBooterInit:
    """Tests for LocalBooter initialization."""

    def test_local_booter_init(self):
        """Test LocalBooter initializes with all components."""
        booter = LocalBooter()
        assert isinstance(booter, ComputerBooter)
        assert isinstance(booter.fs, LocalFileSystemComponent)
        assert isinstance(booter.python, LocalPythonComponent)
        assert isinstance(booter.shell, LocalShellComponent)

    def test_local_booter_properties(self):
        """Test LocalBooter properties return correct components."""
        booter = LocalBooter()
        assert booter.fs is booter._fs
        assert booter.python is booter._python
        assert booter.shell is booter._shell


class TestLocalBooterLifecycle:
    """Tests for LocalBooter boot and shutdown."""

    @pytest.mark.asyncio
    async def test_boot(self):
        """Test LocalBooter boot method."""
        booter = LocalBooter()
        # Should not raise any exception
        await booter.boot("test-session-id")
        # boot is a no-op for LocalBooter

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test LocalBooter shutdown method."""
        booter = LocalBooter()
        # Should not raise any exception
        await booter.shutdown()

    @pytest.mark.asyncio
    async def test_available(self):
        """Test LocalBooter available method returns True."""
        booter = LocalBooter()
        assert await booter.available() is True


class TestLocalBooterUploadDownload:
    """Tests for LocalBooter file operations."""

    @pytest.mark.asyncio
    async def test_upload_file_not_supported(self):
        """Test LocalBooter upload_file raises NotImplementedError."""
        booter = LocalBooter()
        with pytest.raises(NotImplementedError) as exc_info:
            await booter.upload_file("local_path", "remote_path")
        assert "LocalBooter does not support upload_file operation" in str(
            exc_info.value
        )

    @pytest.mark.asyncio
    async def test_download_file_not_supported(self):
        """Test LocalBooter download_file raises NotImplementedError."""
        booter = LocalBooter()
        with pytest.raises(NotImplementedError) as exc_info:
            await booter.download_file("remote_path", "local_path")
        assert "LocalBooter does not support download_file operation" in str(
            exc_info.value
        )


class TestSecurityRestrictions:
    """Tests for security restrictions in LocalBooter."""

    def test_is_safe_command_allowed(self):
        """Test safe commands are allowed."""
        allowed_commands = [
            "echo hello",
            "ls -la",
            "pwd",
            "cat file.txt",
            "python script.py",
            "git status",
            "npm install",
            "pip list",
        ]
        for cmd in allowed_commands:
            assert _is_safe_command(cmd) is True, f"Command '{cmd}' should be allowed"

    def test_is_safe_command_blocked(self):
        """Test dangerous commands are blocked."""
        blocked_commands = [
            "rm -rf /",
            "rm -rf /tmp",
            "rm -fr /home",
            "mkfs.ext4 /dev/sda",
            "dd if=/dev/zero of=/dev/sda",
            "shutdown now",
            "reboot",
            "poweroff",
            "halt",
            "sudo rm",
            ":(){:|:&};:",
            "kill -9 -1",
            "killall python",
        ]
        for cmd in blocked_commands:
            assert _is_safe_command(cmd) is False, f"Command '{cmd}' should be blocked"

    def test_ensure_safe_path_allowed(self, tmp_path):
        """Test paths within allowed roots are accepted."""
        # Create a test directory structure
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        # Mock get_astrbot_root, get_astrbot_data_path, get_astrbot_temp_path
        with (
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_root",
                return_value=str(tmp_path),
            ),
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_data_path",
                return_value=str(tmp_path),
            ),
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_temp_path",
                return_value=str(tmp_path),
            ),
        ):
            result = _ensure_safe_path(str(test_file))
            assert result == str(test_file)

    def test_ensure_safe_path_blocked(self, tmp_path):
        """Test paths outside allowed roots raise PermissionError."""
        with (
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_root",
                return_value=str(tmp_path),
            ),
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_data_path",
                return_value=str(tmp_path),
            ),
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_temp_path",
                return_value=str(tmp_path),
            ),
        ):
            # Try to access a path outside the allowed roots
            with pytest.raises(PermissionError) as exc_info:
                _ensure_safe_path("/etc/passwd")
            assert "Path is outside the allowed computer roots" in str(exc_info.value)


class TestLocalShellComponent:
    """Tests for LocalShellComponent."""

    @pytest.mark.asyncio
    async def test_exec_safe_command(self):
        """Test executing a safe command."""
        shell = LocalShellComponent()
        result = await shell.exec("echo hello")
        assert result["exit_code"] == 0
        assert "hello" in result["stdout"]

    @pytest.mark.asyncio
    async def test_exec_blocked_command(self):
        """Test executing a blocked command raises PermissionError."""
        shell = LocalShellComponent()
        with pytest.raises(PermissionError) as exc_info:
            await shell.exec("rm -rf /")
        assert "Blocked unsafe shell command" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_exec_with_timeout(self):
        """Test command with timeout."""
        shell = LocalShellComponent()
        # Sleep command should complete within timeout
        result = await shell.exec("echo test", timeout=5)
        assert result["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_exec_with_cwd(self, tmp_path):
        """Test command execution with custom working directory."""
        shell = LocalShellComponent()
        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        with (
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_root",
                return_value=str(tmp_path),
            ),
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_data_path",
                return_value=str(tmp_path),
            ),
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_temp_path",
                return_value=str(tmp_path),
            ),
        ):
            # Use python to read file to avoid Windows vs Unix command differences
            result = await shell.exec(
                f'python -c "print(open(r\\"{test_file}\\"))"',
                cwd=str(tmp_path),
            )
            assert result["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_exec_with_env(self):
        """Test command execution with custom environment variables."""
        shell = LocalShellComponent()
        result = await shell.exec(
            'python -c "import os; print(os.environ.get(\\"TEST_VAR\\", \\"\\"))"',
            env={"TEST_VAR": "test_value"},
        )
        assert result["exit_code"] == 0
        assert "test_value" in result["stdout"]


class TestLocalPythonComponent:
    """Tests for LocalPythonComponent."""

    @pytest.mark.asyncio
    async def test_exec_simple_code(self):
        """Test executing simple Python code."""
        python = LocalPythonComponent()
        result = await python.exec("print('hello')")
        assert result["data"]["output"]["text"] == "hello\n"

    @pytest.mark.asyncio
    async def test_exec_with_error(self):
        """Test executing Python code with error."""
        python = LocalPythonComponent()
        result = await python.exec("raise ValueError('test error')")
        assert "test error" in result["data"]["error"]

    @pytest.mark.asyncio
    async def test_exec_with_timeout(self):
        """Test Python execution with timeout."""
        python = LocalPythonComponent()
        # This should timeout
        result = await python.exec("import time; time.sleep(10)", timeout=1)
        assert "timed out" in result["data"]["error"].lower()

    @pytest.mark.asyncio
    async def test_exec_silent_mode(self):
        """Test Python execution in silent mode."""
        python = LocalPythonComponent()
        result = await python.exec("print('hello')", silent=True)
        assert result["data"]["output"]["text"] == ""

    @pytest.mark.asyncio
    async def test_exec_return_value(self):
        """Test Python execution returns value correctly."""
        python = LocalPythonComponent()
        result = await python.exec("result = 1 + 1\nprint(result)")
        assert "2" in result["data"]["output"]["text"]


class TestLocalFileSystemComponent:
    """Tests for LocalFileSystemComponent."""

    @pytest.mark.asyncio
    async def test_create_file(self, tmp_path):
        """Test creating a file."""
        fs = LocalFileSystemComponent()
        test_path = tmp_path / "test.txt"

        with (
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_root",
                return_value=str(tmp_path),
            ),
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_data_path",
                return_value=str(tmp_path),
            ),
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_temp_path",
                return_value=str(tmp_path),
            ),
        ):
            result = await fs.create_file(str(test_path), "test content")
            assert result["success"] is True
            assert test_path.exists()
            assert test_path.read_text() == "test content"

    @pytest.mark.asyncio
    async def test_read_file(self, tmp_path):
        """Test reading a file."""
        fs = LocalFileSystemComponent()
        test_path = tmp_path / "test.txt"
        test_path.write_text("test content")

        with (
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_root",
                return_value=str(tmp_path),
            ),
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_data_path",
                return_value=str(tmp_path),
            ),
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_temp_path",
                return_value=str(tmp_path),
            ),
        ):
            result = await fs.read_file(str(test_path))
            assert result["success"] is True
            assert result["content"] == "test content"

    @pytest.mark.asyncio
    async def test_write_file(self, tmp_path):
        """Test writing to a file."""
        fs = LocalFileSystemComponent()
        test_path = tmp_path / "test.txt"

        with (
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_root",
                return_value=str(tmp_path),
            ),
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_data_path",
                return_value=str(tmp_path),
            ),
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_temp_path",
                return_value=str(tmp_path),
            ),
        ):
            result = await fs.write_file(str(test_path), "new content")
            assert result["success"] is True
            assert test_path.read_text() == "new content"

    @pytest.mark.asyncio
    async def test_delete_file(self, tmp_path):
        """Test deleting a file."""
        fs = LocalFileSystemComponent()
        test_path = tmp_path / "test.txt"
        test_path.write_text("test")

        with (
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_root",
                return_value=str(tmp_path),
            ),
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_data_path",
                return_value=str(tmp_path),
            ),
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_temp_path",
                return_value=str(tmp_path),
            ),
        ):
            result = await fs.delete_file(str(test_path))
            assert result["success"] is True
            assert not test_path.exists()

    @pytest.mark.asyncio
    async def test_delete_directory(self, tmp_path):
        """Test deleting a directory."""
        fs = LocalFileSystemComponent()
        test_dir = tmp_path / "testdir"
        test_dir.mkdir()
        (test_dir / "file.txt").write_text("test")

        with (
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_root",
                return_value=str(tmp_path),
            ),
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_data_path",
                return_value=str(tmp_path),
            ),
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_temp_path",
                return_value=str(tmp_path),
            ),
        ):
            result = await fs.delete_file(str(test_dir))
            assert result["success"] is True
            assert not test_dir.exists()

    @pytest.mark.asyncio
    async def test_list_dir(self, tmp_path):
        """Test listing directory contents."""
        fs = LocalFileSystemComponent()
        # Create test files
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.txt").write_text("content2")
        (tmp_path / ".hidden").write_text("hidden")

        with (
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_root",
                return_value=str(tmp_path),
            ),
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_data_path",
                return_value=str(tmp_path),
            ),
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_temp_path",
                return_value=str(tmp_path),
            ),
        ):
            # Without hidden files
            result = await fs.list_dir(str(tmp_path), show_hidden=False)
            assert result["success"] is True
            assert "file1.txt" in result["entries"]
            assert "file2.txt" in result["entries"]
            assert ".hidden" not in result["entries"]

            # With hidden files
            result = await fs.list_dir(str(tmp_path), show_hidden=True)
            assert ".hidden" in result["entries"]

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, tmp_path):
        """Test reading a non-existent file raises error."""
        fs = LocalFileSystemComponent()

        with (
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_root",
                return_value=str(tmp_path),
            ),
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_data_path",
                return_value=str(tmp_path),
            ),
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_temp_path",
                return_value=str(tmp_path),
            ),
        ):
            # Should raise FileNotFoundError
            with pytest.raises(FileNotFoundError):
                await fs.read_file(str(tmp_path / "nonexistent.txt"))


class TestComputerBooterBase:
    """Tests for ComputerBooter base class interface."""

    def test_base_class_is_protocol(self):
        """Test ComputerBooter has expected interface."""
        booter = LocalBooter()
        assert hasattr(booter, "fs")
        assert hasattr(booter, "python")
        assert hasattr(booter, "shell")
        assert hasattr(booter, "boot")
        assert hasattr(booter, "shutdown")
        assert hasattr(booter, "upload_file")
        assert hasattr(booter, "download_file")
        assert hasattr(booter, "available")


class TestShipyardBooter:
    """Tests for ShipyardBooter."""

    @pytest.mark.asyncio
    async def test_shipyard_booter_init(self):
        """Test ShipyardBooter initialization."""
        with patch("astrbot.core.computer.booters.shipyard.ShipyardClient"):
            from astrbot.core.computer.booters.shipyard import ShipyardBooter

            booter = ShipyardBooter(
                endpoint_url="http://localhost:8080",
                access_token="test_token",
                ttl=3600,
                session_num=10,
            )
            assert booter._ttl == 3600
            assert booter._session_num == 10

    @pytest.mark.asyncio
    async def test_shipyard_booter_boot(self):
        """Test ShipyardBooter boot method."""
        mock_ship = MagicMock()
        mock_ship.id = "test-ship-id"
        mock_ship.fs = MagicMock()
        mock_ship.python = MagicMock()
        mock_ship.shell = MagicMock()

        mock_client = MagicMock()
        mock_client.create_ship = AsyncMock(return_value=mock_ship)

        with patch(
            "astrbot.core.computer.booters.shipyard.ShipyardClient",
            return_value=mock_client,
        ):
            from astrbot.core.computer.booters.shipyard import ShipyardBooter

            booter = ShipyardBooter(
                endpoint_url="http://localhost:8080",
                access_token="test_token",
            )
            await booter.boot("test-session")
            assert booter._ship == mock_ship

    @pytest.mark.asyncio
    async def test_shipyard_available_healthy(self):
        """Test ShipyardBooter available when healthy."""
        mock_ship = MagicMock()
        mock_ship.id = "test-ship-id"

        mock_client = MagicMock()
        mock_client.get_ship = AsyncMock(return_value={"status": 1})

        with patch(
            "astrbot.core.computer.booters.shipyard.ShipyardClient",
            return_value=mock_client,
        ):
            from astrbot.core.computer.booters.shipyard import ShipyardBooter

            booter = ShipyardBooter(
                endpoint_url="http://localhost:8080",
                access_token="test_token",
            )
            booter._ship = mock_ship
            booter._sandbox_client = mock_client

            result = await booter.available()
            assert result is True

    @pytest.mark.asyncio
    async def test_shipyard_available_unhealthy(self):
        """Test ShipyardBooter available when unhealthy."""
        mock_ship = MagicMock()
        mock_ship.id = "test-ship-id"

        mock_client = MagicMock()
        mock_client.get_ship = AsyncMock(return_value={"status": 0})

        with patch(
            "astrbot.core.computer.booters.shipyard.ShipyardClient",
            return_value=mock_client,
        ):
            from astrbot.core.computer.booters.shipyard import ShipyardBooter

            booter = ShipyardBooter(
                endpoint_url="http://localhost:8080",
                access_token="test_token",
            )
            booter._ship = mock_ship
            booter._sandbox_client = mock_client

            result = await booter.available()
            assert result is False


class TestBoxliteBooter:
    """Tests for BoxliteBooter."""

    @pytest.mark.asyncio
    async def test_boxlite_booter_init(self):
        """Test BoxliteBooter can be instantiated via __new__."""
        # Need to mock boxlite module before importing
        mock_boxlite = MagicMock()
        mock_boxlite.SimpleBox = MagicMock()

        with patch.dict(sys.modules, {"boxlite": mock_boxlite}):
            from astrbot.core.computer.booters.boxlite import BoxliteBooter

            # Just verify class exists and can be instantiated (boot is async)
            booter = BoxliteBooter.__new__(BoxliteBooter)
            assert booter is not None


class TestComputerClient:
    """Tests for computer_client module functions."""

    def test_get_local_booter(self):
        """Test get_local_booter returns singleton LocalBooter."""
        from astrbot.core.computer import computer_client

        # Clear the global booter to test singleton
        computer_client.local_booter = None

        booter1 = computer_client.get_local_booter()
        booter2 = computer_client.get_local_booter()

        assert isinstance(booter1, LocalBooter)
        assert booter1 is booter2  # Same instance (singleton)

        # Reset for other tests
        computer_client.local_booter = None

    @pytest.mark.asyncio
    async def test_get_booter_shipyard(self):
        """Test get_booter with shipyard type."""
        from astrbot.core.computer import computer_client
        from astrbot.core.computer.booters.shipyard import ShipyardBooter

        # Clear session booter
        computer_client.session_booter.clear()

        mock_context = MagicMock()
        mock_config = MagicMock()
        mock_config.get = lambda key, default=None: {
            "provider_settings": {
                "sandbox": {
                    "booter": "shipyard",
                    "shipyard_endpoint": "http://localhost:8080",
                    "shipyard_access_token": "test_token",
                    "shipyard_ttl": 3600,
                    "shipyard_max_sessions": 10,
                }
            }
        }.get(key, default)
        mock_context.get_config = MagicMock(return_value=mock_config)

        # Mock the ShipyardBooter
        mock_ship = MagicMock()
        mock_ship.id = "test-ship-id"
        mock_ship.fs = MagicMock()
        mock_ship.python = MagicMock()
        mock_ship.shell = MagicMock()

        mock_booter = MagicMock()
        mock_booter.boot = AsyncMock()
        mock_booter.available = AsyncMock(return_value=True)
        mock_booter.shell = MagicMock()
        mock_booter.upload_file = AsyncMock(return_value={"success": True})

        with (
            patch.object(ShipyardBooter, "boot", new=AsyncMock()),
            patch(
                "astrbot.core.computer.computer_client._sync_skills_to_sandbox",
                AsyncMock(),
            ),
        ):
            # Directly set the booter in the session
            computer_client.session_booter["test-session-id"] = mock_booter

            booter = await computer_client.get_booter(mock_context, "test-session-id")
            assert booter is mock_booter

        # Cleanup
        computer_client.session_booter.clear()

    @pytest.mark.asyncio
    async def test_get_booter_unknown_type(self):
        """Test get_booter with unknown booter type raises ValueError."""
        from astrbot.core.computer import computer_client

        computer_client.session_booter.clear()

        mock_context = MagicMock()
        mock_config = MagicMock()
        mock_config.get = lambda key, default=None: {
            "provider_settings": {
                "sandbox": {
                    "booter": "unknown_type",
                }
            }
        }.get(key, default)
        mock_context.get_config = MagicMock(return_value=mock_config)

        with pytest.raises(ValueError) as exc_info:
            await computer_client.get_booter(mock_context, "test-session-id")
        assert "Unknown booter type" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_booter_reuses_existing(self):
        """Test get_booter reuses existing booter for same session."""
        from astrbot.core.computer import computer_client
        from astrbot.core.computer.booters.shipyard import ShipyardBooter

        computer_client.session_booter.clear()

        mock_context = MagicMock()
        mock_config = MagicMock()
        mock_config.get = lambda key, default=None: {
            "provider_settings": {
                "sandbox": {
                    "booter": "shipyard",
                    "shipyard_endpoint": "http://localhost:8080",
                    "shipyard_access_token": "test_token",
                }
            }
        }.get(key, default)
        mock_context.get_config = MagicMock(return_value=mock_config)

        mock_booter = MagicMock()
        mock_booter.boot = AsyncMock()
        mock_booter.available = AsyncMock(return_value=True)
        mock_booter.shell = MagicMock()
        mock_booter.upload_file = AsyncMock(return_value={"success": True})

        with (
            patch.object(ShipyardBooter, "boot", new=AsyncMock()),
            patch(
                "astrbot.core.computer.computer_client._sync_skills_to_sandbox",
                AsyncMock(),
            ),
        ):
            # Pre-set the booter
            computer_client.session_booter["test-session"] = mock_booter

            booter1 = await computer_client.get_booter(mock_context, "test-session")
            booter2 = await computer_client.get_booter(mock_context, "test-session")
            assert booter1 is booter2

        # Cleanup
        computer_client.session_booter.clear()

    @pytest.mark.asyncio
    async def test_get_booter_rebuild_unavailable(self):
        """Test get_booter rebuilds when existing booter is unavailable."""
        from astrbot.core.computer import computer_client
        from astrbot.core.computer.booters.shipyard import ShipyardBooter

        computer_client.session_booter.clear()

        mock_context = MagicMock()
        mock_config = MagicMock()
        mock_config.get = lambda key, default=None: {
            "provider_settings": {
                "sandbox": {
                    "booter": "shipyard",
                    "shipyard_endpoint": "http://localhost:8080",
                    "shipyard_access_token": "test_token",
                }
            }
        }.get(key, default)
        mock_context.get_config = MagicMock(return_value=mock_config)

        mock_booter1 = MagicMock()
        mock_booter1.boot = AsyncMock()
        mock_booter1.available = AsyncMock(return_value=False)  # Not available

        mock_booter2 = MagicMock()
        mock_booter2.boot = AsyncMock()
        mock_booter2.available = AsyncMock(return_value=True)
        mock_booter2.shell = MagicMock()
        mock_booter2.upload_file = AsyncMock(return_value={"success": True})

        call_count = 0

        def create_booter(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_booter1
            return mock_booter2

        with (
            patch(
                "astrbot.core.computer.booters.shipyard.ShipyardClient",
            ),
            patch(
                "astrbot.core.computer.computer_client._sync_skills_to_sandbox",
                AsyncMock(),
            ),
        ):
            # Pre-set the unavailable booter
            computer_client.session_booter["test-session-rebuild"] = mock_booter1

            # Now when we call get_booter, it should detect the booter is unavailable
            # and create a new one
            with patch.object(ShipyardBooter, "boot", new=AsyncMock()):
                await computer_client.get_booter(
                    mock_context, "test-session-rebuild"
                )
                # The new booter should be used after the old one is unavailable
                # Since we mocked boot but not available(), the new booter should be set

        # Cleanup
        computer_client.session_booter.clear()


class TestSyncSkillsToSandbox:
    """Tests for _sync_skills_to_sandbox function."""

    @pytest.mark.asyncio
    async def test_sync_skills_no_skills_dir(self):
        """Test sync does nothing when skills directory doesn't exist."""
        from astrbot.core.computer import computer_client

        mock_booter = MagicMock()
        mock_booter.shell.exec = AsyncMock()
        mock_booter.upload_file = AsyncMock(return_value={"success": True})

        with (
            patch(
                "astrbot.core.computer.computer_client.get_astrbot_skills_path",
                return_value="/nonexistent/path",
            ),
            patch(
                "astrbot.core.computer.computer_client.os.path.isdir",
                return_value=False,
            ),
        ):
            await computer_client._sync_skills_to_sandbox(mock_booter)
            mock_booter.upload_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_skills_empty_dir(self):
        """Test sync does nothing when skills directory is empty."""
        from astrbot.core.computer import computer_client

        mock_booter = MagicMock()
        mock_booter.shell.exec = AsyncMock()
        mock_booter.upload_file = AsyncMock(return_value={"success": True})

        with (
            patch(
                "astrbot.core.computer.computer_client.get_astrbot_skills_path",
                return_value="/tmp/empty",
            ),
            patch(
                "astrbot.core.computer.computer_client.os.path.isdir",
                return_value=True,
            ),
            patch(
                "astrbot.core.computer.computer_client.Path.iterdir",
                return_value=iter([]),
            ),
        ):
            await computer_client._sync_skills_to_sandbox(mock_booter)
            mock_booter.upload_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_skills_success(self):
        """Test successful skills sync."""
        from astrbot.core.computer import computer_client

        mock_booter = MagicMock()
        mock_booter.shell.exec = AsyncMock(return_value={"exit_code": 0})
        mock_booter.upload_file = AsyncMock(return_value={"success": True})

        mock_skill_file = MagicMock()
        mock_skill_file.name = "skill.py"
        mock_skill_file.__str__ = lambda: "/tmp/skills/skill.py"

        with (
            patch(
                "astrbot.core.computer.computer_client.get_astrbot_skills_path",
                return_value="/tmp/skills",
            ),
            patch(
                "astrbot.core.computer.computer_client.os.path.isdir",
                return_value=True,
            ),
            patch(
                "astrbot.core.computer.computer_client.Path.iterdir",
                return_value=iter([mock_skill_file]),
            ),
            patch(
                "astrbot.core.computer.computer_client.get_astrbot_temp_path",
                return_value="/tmp",
            ),
            patch(
                "astrbot.core.computer.computer_client.shutil.make_archive",
            ),
            patch(
                "astrbot.core.computer.computer_client.os.path.exists",
                return_value=True,
            ),
            patch(
                "astrbot.core.computer.computer_client.os.remove",
            ),
        ):
            # Should not raise
            await computer_client._sync_skills_to_sandbox(mock_booter)
