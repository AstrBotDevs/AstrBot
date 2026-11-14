"""Tests for the built-in runtime computer module.

This module tests the ComputerClient, Booter implementations (local, shipyard, boxlite),
filesystem operations, Python execution, shell execution, and security restrictions.
"""

import asyncio
import json
import os
import re
import shlex
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from astrbot.core.astr_agent_runtime.computer.booters.base import ComputerBooter
from astrbot.core.astr_agent_runtime.computer.booters.local import (
    LocalBooter,
    LocalFileSystemComponent,
    LocalPythonComponent,
    LocalShellComponent,
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
        booter._shell.shutdown_sessions = AsyncMock()

        await booter.shutdown()

        booter._shell.shutdown_sessions.assert_awaited_once()

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
                "astrbot.core.astr_agent_runtime.computer.booters.local.get_astrbot_root",
                return_value=str(tmp_path),
            ),
        ):
            # Build a per-shell command: PowerShell needs the call operator
            # (&) for quoted, space-containing executables; POSIX shells take
            # the plain quoted form.
            if os.name == "nt":
                command = (
                    f"& '{sys.executable}' -c \"print(open(r'{test_file}').read())\""
                )
            else:
                command = (
                    f"{shlex.quote(sys.executable)} -c "
                    f'"print(open({str(test_file)!r}).read())"'
                )
            result = await shell.exec(
                command,
                cwd=str(tmp_path),
            )
            assert result["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_exec_with_env(self):
        """Test command execution with custom environment variables."""
        shell = LocalShellComponent()
        if os.name == "nt":
            command = (
                f"& '{sys.executable}' -c "
                "\"import os; print(os.environ.get('TEST_VAR', ''))\""
            )
        else:
            command = (
                f"{shlex.quote(sys.executable)} -c "
                "\"import os; print(os.environ.get('TEST_VAR', ''))\""
            )
        result = await shell.exec(
            command,
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
                "astrbot.core.astr_agent_runtime.computer.booters.local.get_astrbot_root",
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
                "astrbot.core.astr_agent_runtime.computer.booters.local.get_astrbot_root",
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
                "astrbot.core.astr_agent_runtime.computer.booters.local.get_astrbot_root",
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
                "astrbot.core.astr_agent_runtime.computer.booters.local.get_astrbot_root",
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
                "astrbot.core.astr_agent_runtime.computer.booters.local.get_astrbot_root",
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
                "astrbot.core.astr_agent_runtime.computer.booters.local.get_astrbot_root",
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
                "astrbot.core.astr_agent_runtime.computer.booters.local.get_astrbot_root",
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
    async def test_shipyard_shell_unwraps_bay_exec_response(self):
        """Bay exec responses keep shell output under the data field."""
        from astrbot.core.astr_agent_runtime.computer.booters.shipyard import (
            ShipyardShellWrapper,
        )

        raw_shell = MagicMock()
        raw_shell.exec = AsyncMock(
            return_value={
                "success": True,
                "data": {
                    "success": True,
                    "return_code": 0,
                    "stdout": "hello_from_shipyard_bay\n/workspace\n",
                    "stderr": "",
                    "pid": 16,
                    "process_id": None,
                    "error": None,
                },
                "error": None,
            },
        )

        result = await ShipyardShellWrapper(raw_shell).exec(
            "echo hello_from_shipyard_bay && pwd"
        )

        assert result["stdout"] == "hello_from_shipyard_bay\n/workspace\n"
        assert result["stderr"] == ""
        assert result["exit_code"] == 0
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_shipyard_shell_keeps_flat_exec_response_compatible(self):
        """Flat shell responses remain compatible with ShipyardShellWrapper."""
        from astrbot.core.astr_agent_runtime.computer.booters.shipyard import (
            ShipyardShellWrapper,
        )

        raw_shell = MagicMock()
        raw_shell.exec = AsyncMock(
            return_value={
                "success": True,
                "stdout": "hello_from_legacy_shell\n/workspace\n",
                "stderr": "",
                "exit_code": 0,
                "execution_id": "exec-legacy",
                "execution_time_ms": 45,
                "command": "echo hello_from_legacy_shell && pwd",
            },
        )

        result = await ShipyardShellWrapper(raw_shell).exec(
            "echo hello_from_legacy_shell && pwd"
        )

        assert result == {
            "stdout": "hello_from_legacy_shell\n/workspace\n",
            "stderr": "",
            "exit_code": 0,
            "success": True,
            "execution_id": "exec-legacy",
            "execution_time_ms": 45,
            "command": "echo hello_from_legacy_shell && pwd",
        }

    @pytest.mark.asyncio
    async def test_shipyard_shell_maps_nonzero_return_code(self):
        """A non-zero Bay return_code is exposed as exit_code and failure."""
        from astrbot.core.astr_agent_runtime.computer.booters.shipyard import (
            ShipyardShellWrapper,
        )

        raw_shell = MagicMock()
        raw_shell.exec = AsyncMock(
            return_value={
                "success": True,
                "data": {
                    "success": False,
                    "return_code": 3,
                    "stdout": "",
                    "stderr": "oops",
                },
                "error": None,
            },
        )

        result = await ShipyardShellWrapper(raw_shell).exec("echo oops >&2; exit 3")

        assert result["stdout"] == ""
        assert result["stderr"] == "oops"
        assert result["exit_code"] == 3
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_shipyard_shell_failure_without_success_field(self):
        """A nonzero return code without `success` is reported as a failure."""
        from astrbot.core.astr_agent_runtime.computer.booters.shipyard import (
            ShipyardShellWrapper,
        )

        raw_shell = MagicMock()
        raw_shell.exec = AsyncMock(
            return_value={"data": {"return_code": 1, "stdout": "", "stderr": ""}}
        )

        result = await ShipyardShellWrapper(raw_shell).exec("false")

        assert result["exit_code"] == 1
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_shipyard_shell_keeps_envelope_error(self):
        """A nested `data.error = None` must not hide the envelope error."""
        from astrbot.core.astr_agent_runtime.computer.booters.shipyard import (
            ShipyardShellWrapper,
        )

        raw_shell = MagicMock()
        raw_shell.exec = AsyncMock(
            return_value={
                "success": False,
                "data": {
                    "success": False,
                    "return_code": 1,
                    "stdout": "",
                    "stderr": "",
                    "error": None,
                },
                "error": "Ship returned 500: exec failed",
            },
        )

        result = await ShipyardShellWrapper(raw_shell).exec("false")

        assert result["stderr"] == "Ship returned 500: exec failed"
        assert result["exit_code"] == 1
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_shipyard_file_tools_unwrap_bay_exec_response(self):
        """Bay file responses keep their payload under the data field too."""
        from astrbot.core.astr_agent_runtime.computer.booters.shipyard import (
            ShipyardFileSystemWrapper,
        )

        raw_fs = MagicMock()
        raw_fs.read_file = AsyncMock(
            return_value={
                "success": True,
                "data": {"content": "hello-file", "path": "probe.txt", "size": 10},
                "error": None,
            },
        )
        raw_fs.list_dir = AsyncMock(
            return_value={
                "success": True,
                "data": {
                    "files": [{"name": "probe.txt", "is_file": True}],
                    "current_path": "/workspace",
                },
                "error": None,
            },
        )

        wrapper = ShipyardFileSystemWrapper(raw_fs, MagicMock())

        read_result = await wrapper.read_file("probe.txt")
        assert read_result["content"] == "hello-file"
        assert "data" not in read_result

        list_result = await wrapper.list_dir(".")
        assert list_result["files"] == [{"name": "probe.txt", "is_file": True}]
        assert list_result["current_path"] == "/workspace"
        assert "data" not in list_result

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("method", "kwargs", "inner"),
        [
            (
                "create_file",
                {"path": "probe.txt", "content": "hello-file"},
                {"success": True, "path": "probe.txt", "size": 10},
            ),
            (
                "write_file",
                {"path": "probe.txt", "content": "hello-file"},
                {"success": True, "path": "probe.txt", "bytes_written": 10},
            ),
            (
                "delete_file",
                {"path": "probe.txt"},
                {"success": True, "path": "probe.txt"},
            ),
            (
                "edit_file",
                {"path": "probe.txt", "old_string": "a", "new_string": "b"},
                {"success": True, "replacements": 1},
            ),
        ],
    )
    async def test_shipyard_remaining_file_tools_unwrap_bay_exec_response(
        self, method, kwargs, inner
    ):
        """Every fs wrapper flattens the envelope, not only read_file/list_dir."""
        from astrbot.core.astr_agent_runtime.computer.booters.shipyard import (
            ShipyardFileSystemWrapper,
        )

        raw_fs = MagicMock()
        setattr(
            raw_fs,
            method,
            AsyncMock(return_value={"success": True, "data": inner, "error": None}),
        )

        wrapper = ShipyardFileSystemWrapper(raw_fs, MagicMock())
        result = await getattr(wrapper, method)(**kwargs)

        for key, value in inner.items():
            assert result[key] == value
        assert "data" not in result

    @pytest.mark.asyncio
    async def test_shipyard_shell_envelope_failure_wins_over_data_success(self):
        """A failed request is not reported as a success by data.success."""
        from astrbot.core.astr_agent_runtime.computer.booters.shipyard import (
            ShipyardShellWrapper,
        )

        raw_shell = MagicMock()
        raw_shell.exec = AsyncMock(
            return_value={
                "success": False,
                "data": {
                    "success": True,
                    "return_code": 0,
                    "stdout": "stale-body",
                    "stderr": "",
                    "error": None,
                },
                "error": "Ship returned 500: exec failed",
            },
        )

        result = await ShipyardShellWrapper(raw_shell).exec("echo hi")

        assert result["success"] is False
        assert result["stderr"] == "Ship returned 500: exec failed"

    @pytest.mark.asyncio
    async def test_shipyard_shell_envelope_failure_without_data(self):
        """A request-level failure carrying no `data` is still a failure."""
        from astrbot.core.astr_agent_runtime.computer.booters.shipyard import (
            ShipyardShellWrapper,
        )

        raw_shell = MagicMock()
        raw_shell.exec = AsyncMock(
            return_value={
                "success": False,
                "data": None,
                "error": "Ship returned 500: exec failed",
            },
        )

        result = await ShipyardShellWrapper(raw_shell).exec("echo hi")

        assert result["stdout"] == ""
        assert result["stderr"] == "Ship returned 500: exec failed"
        assert result["exit_code"] is None
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_shipyard_booter_init(self):
        """Test ShipyardBooter initialization."""
        with patch("astrbot.core.astr_agent_runtime.computer.booters.shipyard.ShipyardClient"):
            from astrbot.core.astr_agent_runtime.computer.booters.shipyard import (
                ShipyardBooter,
            )

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
            "astrbot.core.astr_agent_runtime.computer.booters.shipyard.ShipyardClient",
            return_value=mock_client,
        ):
            from astrbot.core.astr_agent_runtime.computer.booters.shipyard import (
                ShipyardBooter,
            )

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
            "astrbot.core.astr_agent_runtime.computer.booters.shipyard.ShipyardClient",
            return_value=mock_client,
        ):
            from astrbot.core.astr_agent_runtime.computer.booters.shipyard import (
                ShipyardBooter,
            )

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
            "astrbot.core.astr_agent_runtime.computer.booters.shipyard.ShipyardClient",
            return_value=mock_client,
        ):
            from astrbot.core.astr_agent_runtime.computer.booters.shipyard import (
                ShipyardBooter,
            )

            booter = ShipyardBooter(
                endpoint_url="http://localhost:8080",
                access_token="test_token",
            )
            booter._ship = mock_ship
            booter._sandbox_client = mock_client

            result = await booter.available()
            assert result is False


class _MockResponse:
    def __init__(self, status=200, text_data="", json_data=None, chunks=None):
        self.status = status
        self._text = text_data
        self._json = json_data or {}
        self._chunks = chunks or []

        class _Content:
            def __init__(self, chunks):
                self._chunks = chunks

            def iter_chunked(self, size=65536):
                async def _gen():
                    for chunk in self._chunks:
                        yield chunk

                return _gen()

        self.content = _Content(self._chunks)

    async def text(self):
        return self._text

    async def json(self):
        return self._json


class _MockClientSession:
    def __init__(self, response=None, get_resp=None, post_resp=None, side_effect=None):
        self._resp = response or _MockResponse()
        self._get_resp = get_resp or self._resp
        self._post_resp = post_resp or self._resp
        self._side_effect = side_effect
        self.last_get = None
        self.last_post = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None

    def get(self, url, **kwargs):
        if self._side_effect:
            raise self._side_effect
        self.last_get = (url, kwargs)

        if callable(self._get_resp):
            resp = self._get_resp(url, **kwargs)
        elif isinstance(self._get_resp, list):
            resp = self._get_resp.pop(0) if self._get_resp else self._resp
        else:
            resp = self._get_resp

        if isinstance(resp, Exception):
            raise resp

        class _RequestContext:
            def __init__(self, resp):
                self.resp = resp

            async def __aenter__(self):
                return self.resp

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        return _RequestContext(resp)

    def post(self, url, **kwargs):
        if self._side_effect:
            raise self._side_effect
        self.last_post = (url, kwargs)

        class _RequestContext:
            def __init__(self, resp):
                self.resp = resp

            async def __aenter__(self):
                return self.resp

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        return _RequestContext(self._post_resp)


class TestBoxliteBooter:
    """Tests for BoxliteBooter and related helper classes."""

    @pytest.mark.asyncio
    async def test_boxlite_booter_init(self):
        """Test BoxliteBooter can be instantiated and has initial state."""
        mock_boxlite = MagicMock()
        mock_boxlite.SimpleBox = MagicMock()

        with patch.dict(sys.modules, {"boxlite": mock_boxlite}):
            from astrbot.core.astr_agent_runtime.computer.booters.boxlite import (
                BoxliteBooter,
            )

            booter = BoxliteBooter()
            assert booter is not None
            assert booter._closed is False
            assert booter.box is None
            assert booter.mocked is None
            assert booter._python is None
            assert booter._shell is None
            assert booter._fs is None
            assert booter.capabilities is None

            with pytest.raises(RuntimeError, match="not initialized"):
                _ = booter.fs
            with pytest.raises(RuntimeError, match="not initialized"):
                _ = booter.python
            with pytest.raises(RuntimeError, match="not initialized"):
                _ = booter.shell

    def test_normalize_sandbox_path_valid(self):
        """Test _normalize_sandbox_path converts legitimate paths to workspace-relative."""
        mock_boxlite = MagicMock()
        with patch.dict(sys.modules, {"boxlite": mock_boxlite}):
            from astrbot.core.astr_agent_runtime.computer.booters.boxlite import (
                _normalize_sandbox_path,
            )

            assert (
                _normalize_sandbox_path("/workspace/skills/skills.zip")
                == "skills/skills.zip"
            )
            assert (
                _normalize_sandbox_path("/home/ship_123/workspace/data/test.csv")
                == "data/test.csv"
            )
            assert _normalize_sandbox_path("workspace/foo.txt") == "foo.txt"
            assert (
                _normalize_sandbox_path("relative/path/file.py")
                == "relative/path/file.py"
            )
            assert (
                _normalize_sandbox_path("\\workspace\\nested\\file.py")
                == "nested/file.py"
            )
            assert (
                _normalize_sandbox_path("\\home\\ship_abc\\workspace\\report.xlsx")
                == "report.xlsx"
            )
            assert (
                _normalize_sandbox_path("   /workspace/trimmed.txt   ")
                == "trimmed.txt"
            )
            assert (
                _normalize_sandbox_path("nested/dir/../file.txt")
                == "nested/file.txt"
            )

    def test_normalize_sandbox_path_rejections(self):
        """Test _normalize_sandbox_path rejects traversal, external paths, and empty targets."""
        mock_boxlite = MagicMock()
        with patch.dict(sys.modules, {"boxlite": mock_boxlite}):
            from astrbot.core.astr_agent_runtime.computer.booters.boxlite import (
                _normalize_sandbox_path,
            )

            # 1. Empty and whitespace paths
            with pytest.raises(ValueError, match="cannot be empty"):
                _normalize_sandbox_path("")
            with pytest.raises(ValueError, match="cannot be empty"):
                _normalize_sandbox_path("   ")

            # 2. Workspace root targets without filename
            with pytest.raises(ValueError, match="Invalid target path"):
                _normalize_sandbox_path("/workspace")
            with pytest.raises(ValueError, match="Invalid target path"):
                _normalize_sandbox_path("workspace")
            with pytest.raises(ValueError, match="Invalid target path"):
                _normalize_sandbox_path("/workspace/")

            # 3. POSIX directory traversal attempts
            with pytest.raises(ValueError, match="Path traversal attempt detected"):
                _normalize_sandbox_path("../../etc/passwd")
            with pytest.raises(ValueError, match="Path traversal attempt detected"):
                _normalize_sandbox_path("/workspace/../../etc/shadow")
            with pytest.raises(ValueError, match="Path traversal attempt detected"):
                _normalize_sandbox_path("sub/../../escape")

            # 4. Windows-style directory traversal attempts
            with pytest.raises(ValueError, match="Path traversal attempt detected"):
                _normalize_sandbox_path("..\\..\\windows\\system32")
            with pytest.raises(ValueError, match="Path traversal attempt detected"):
                _normalize_sandbox_path("\\workspace\\..\\..\\secret")

            # 5. External absolute paths outside workspace
            with pytest.raises(ValueError, match="Path outside workspace"):
                _normalize_sandbox_path("/etc/passwd")
            with pytest.raises(ValueError, match="Path outside workspace"):
                _normalize_sandbox_path("/var/log/syslog")
            with pytest.raises(ValueError, match="Path outside workspace"):
                _normalize_sandbox_path("/root/.bashrc")

    @pytest.mark.asyncio
    async def test_upload_file_url_and_headers_and_path(self, tmp_path):
        """Test upload_file fixes URL scheme, adds X-SESSION-ID, and normalizes path."""
        mock_boxlite = MagicMock()
        with patch.dict(sys.modules, {"boxlite": mock_boxlite}):
            from astrbot.core.astr_agent_runtime.computer.booters.boxlite import (
                MockShipyardSandboxClient,
            )

            client = MockShipyardSandboxClient(
                sb_url="http://127.0.0.1:25000",
                session_id="session-42",
            )
            test_file = tmp_path / "sample.txt"
            test_file.write_text("sample content")

            mock_session = _MockClientSession(response=_MockResponse(status=200))
            with patch("aiohttp.ClientSession", return_value=mock_session):
                result = await client.upload_file(
                    str(test_file), "/workspace/nested/dest.txt"
                )

                assert result["success"] is True
                assert result["file_path"] == "nested/dest.txt"

                assert mock_session.last_post is not None
                url, kwargs = mock_session.last_post
                assert url == "http://127.0.0.1:25000/upload"
                assert not url.startswith("http://http://")

                headers = kwargs.get("headers", {})
                assert headers.get("X-SESSION-ID") == "session-42"
                assert kwargs.get("data") is not None

    @pytest.mark.asyncio
    async def test_upload_file_url_normalization(self):
        """Test MockShipyardSandboxClient normalizes url without scheme."""
        mock_boxlite = MagicMock()
        with patch.dict(sys.modules, {"boxlite": mock_boxlite}):
            from astrbot.core.astr_agent_runtime.computer.booters.boxlite import (
                MockShipyardSandboxClient,
            )

            client = MockShipyardSandboxClient(
                sb_url="127.0.0.1:25000/",
                session_id="session-1",
            )
            assert client.sb_url == "http://127.0.0.1:25000"

    @pytest.mark.asyncio
    async def test_upload_file_error_handling(self, tmp_path):
        """Test upload_file catches non-200 responses, timeouts, traversal, and missing files."""
        mock_boxlite = MagicMock()
        with patch.dict(sys.modules, {"boxlite": mock_boxlite}):
            from astrbot.core.astr_agent_runtime.computer.booters.boxlite import (
                MockShipyardSandboxClient,
            )

            client = MockShipyardSandboxClient("http://127.0.0.1:25000")
            test_file = tmp_path / "sample.txt"
            test_file.write_text("sample")

            # 1. Non-200 response
            mock_session_500 = _MockClientSession(
                response=_MockResponse(status=500, text_data="Internal Server Error")
            )
            with patch("aiohttp.ClientSession", return_value=mock_session_500):
                res = await client.upload_file(str(test_file), "sample.txt")
                assert res["success"] is False
                assert "500" in res["error"]

            # 2. Timeout error
            mock_session_timeout = _MockClientSession(
                side_effect=asyncio.TimeoutError()
            )
            with patch("aiohttp.ClientSession", return_value=mock_session_timeout):
                res = await client.upload_file(str(test_file), "sample.txt")
                assert res["success"] is False
                assert "timeout" in res["error"]

            # 3. File not found
            res = await client.upload_file(
                str(tmp_path / "non_existent.txt"), "sample.txt"
            )
            assert res["success"] is False
            assert "File not found" in res["error"]

            # 4. Traversal attempt rejected
            res = await client.upload_file(str(test_file), "../../secret.txt")
            assert res["success"] is False
            assert "traversal" in res["error"].lower()

    @pytest.mark.asyncio
    async def test_boxlite_available(self):
        """Test BoxliteBooter available method under various states."""
        mock_boxlite = MagicMock()
        with patch.dict(sys.modules, {"boxlite": mock_boxlite}):
            from astrbot.core.astr_agent_runtime.computer.booters.boxlite import (
                BoxliteBooter,
                MockShipyardSandboxClient,
            )

            booter = BoxliteBooter()

            # 1. Before boot: returns False
            assert await booter.available() is False

            # 2. After shutdown: returns False
            await booter.shutdown()
            assert await booter.available() is False

            # 3. Healthy sandbox
            booter._closed = False
            booter.mocked = MockShipyardSandboxClient("http://127.0.0.1:25000")
            mock_box = MagicMock()
            mock_box.id = "ship-123"
            mock_box.info = AsyncMock(
                return_value={"status": "running", "running": True}
            )
            booter.box = mock_box

            mock_session_200 = _MockClientSession(response=_MockResponse(status=200))
            with patch("aiohttp.ClientSession", return_value=mock_session_200):
                assert await booter.available() is True

            # 4. Box stopped
            mock_box.info = AsyncMock(
                return_value={"status": "stopped", "running": False}
            )
            assert await booter.available() is False

            # 5. Box info exception
            mock_box.info = AsyncMock(side_effect=RuntimeError("VM crashed"))
            assert await booter.available() is False

            # 6. Health endpoint returns 500
            mock_box.info = AsyncMock(
                return_value={"status": "running", "running": True}
            )
            mock_session_500 = _MockClientSession(response=_MockResponse(status=500))
            with patch("aiohttp.ClientSession", return_value=mock_session_500):
                assert await booter.available() is False

            # 7. Connection error / timeout
            mock_session_err = _MockClientSession(
                side_effect=Exception("Connection refused")
            )
            with patch("aiohttp.ClientSession", return_value=mock_session_err):
                assert await booter.available() is False

    @pytest.mark.asyncio
    async def test_boxlite_available_shutdown_race(self):
        """Test available() returns False if shutdown occurs while health probe is in flight."""
        mock_boxlite = MagicMock()
        with patch.dict(sys.modules, {"boxlite": mock_boxlite}):
            from astrbot.core.astr_agent_runtime.computer.booters.boxlite import (
                BoxliteBooter,
                MockShipyardSandboxClient,
            )

            booter = BoxliteBooter()
            mock_box = MagicMock()
            mock_box.id = "ship-race"
            mock_box.info.return_value = {"status": "running", "running": True}
            mock_box.shutdown = MagicMock()
            booter.box = mock_box
            booter.mocked = MockShipyardSandboxClient("http://127.0.0.1:25000")

            class _RaceClientSession:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    return None

                def get(self, url, **kwargs):
                    class _ReqContext:
                        async def __aenter__(ctx_self):
                            # Trigger shutdown while health request is suspended
                            await booter.shutdown()
                            return _MockResponse(status=200)

                        async def __aexit__(ctx_self, exc_type, exc_val, exc_tb):
                            return None

                    return _ReqContext()

            with patch("aiohttp.ClientSession", return_value=_RaceClientSession()):
                assert await booter.available() is False

    @pytest.mark.asyncio
    async def test_download_file_atomic_and_binary(self, tmp_path):
        """Test download_file streams binary content atomically and cleans temporary files."""
        mock_boxlite = MagicMock()
        with patch.dict(sys.modules, {"boxlite": mock_boxlite}):
            from astrbot.core.astr_agent_runtime.computer.booters.boxlite import (
                BoxliteBooter,
                MockShipyardSandboxClient,
            )

            client = MockShipyardSandboxClient(
                sb_url="http://127.0.0.1:25000",
                session_id="sess-dl",
            )
            booter = BoxliteBooter()
            booter.mocked = client

            binary_payload = b"magic_header\x00\xff\xfe\x01\x02binary_bytes"
            dest_dir = tmp_path / "downloads"
            dest_file = dest_dir / "output.bin"

            # Intercept open to verify uuid-based temp filename
            recorded_temp_paths = []
            import builtins

            real_open = builtins.open

            def _inspect_open(file, *args, **kwargs):
                if ".tmp_" in str(file):
                    recorded_temp_paths.append(str(file))
                return real_open(file, *args, **kwargs)

            mock_session = _MockClientSession(
                response=_MockResponse(status=200, chunks=[binary_payload])
            )
            with (
                patch("aiohttp.ClientSession", return_value=mock_session),
                patch("builtins.open", side_effect=_inspect_open),
            ):
                await booter.download_file("/workspace/sub/remote.bin", str(dest_file))

                assert mock_session.last_get is not None
                url, kwargs = mock_session.last_get
                assert url == "http://127.0.0.1:25000/download"
                assert kwargs["params"] == {"file_path": "sub/remote.bin"}
                assert kwargs["headers"] == {"X-SESSION-ID": "sess-dl"}

                assert dest_file.is_file()
                assert dest_file.read_bytes() == binary_payload

                # Verify temporary staging file used a 32-hex UUID
                assert len(recorded_temp_paths) == 1
                assert re.search(r"\.tmp_output\.bin_[0-9a-f]{32}$", recorded_temp_paths[0]) is not None

                # Ensure no temporary staging files remain
                tmp_files = list(dest_dir.glob(".tmp_*"))
                assert len(tmp_files) == 0

    @pytest.mark.asyncio
    async def test_download_file_failure_cleans_temp_and_preserves_existing(
        self, tmp_path
    ):
        """Test failed download cleans temporary files and preserves existing destination file."""
        mock_boxlite = MagicMock()
        with patch.dict(sys.modules, {"boxlite": mock_boxlite}):
            from astrbot.core.astr_agent_runtime.computer.booters.boxlite import (
                BoxliteBooter,
                MockShipyardSandboxClient,
            )

            client = MockShipyardSandboxClient("http://127.0.0.1:25000")
            booter = BoxliteBooter()
            booter.mocked = client

            dest_dir = tmp_path / "downloads"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_file = dest_dir / "target.txt"
            original_data = b"original untouched content"
            dest_file.write_bytes(original_data)

            # Non-200 download response
            mock_session_500 = _MockClientSession(
                response=_MockResponse(status=500, text_data="Internal error")
            )
            with patch("aiohttp.ClientSession", return_value=mock_session_500):
                with pytest.raises(RuntimeError, match="HTTP 500"):
                    await booter.download_file("remote.txt", str(dest_file))

                # Verify existing destination was preserved untouched
                assert dest_file.read_bytes() == original_data
                # Verify no temporary files remain
                assert len(list(dest_dir.glob(".tmp_*"))) == 0

    @pytest.mark.asyncio
    async def test_download_file_errors(self, tmp_path):
        """Test download_file error handling for uninitialized booter, traversal, and 404."""
        mock_boxlite = MagicMock()
        with patch.dict(sys.modules, {"boxlite": mock_boxlite}):
            from astrbot.core.astr_agent_runtime.computer.booters.boxlite import (
                BoxliteBooter,
                MockShipyardSandboxClient,
            )

            booter = BoxliteBooter()
            # 1. Uninitialized booter raises
            with pytest.raises(RuntimeError, match="not initialized"):
                await booter.download_file("file.txt", str(tmp_path / "out.txt"))

            booter.mocked = MockShipyardSandboxClient("http://127.0.0.1:25000")

            # 2. Empty local_path raises ValueError
            with pytest.raises(ValueError, match="local_path cannot be empty"):
                await booter.download_file("file.txt", "")

            # 3. Path traversal remote path raises ValueError
            with pytest.raises(ValueError, match="Path traversal attempt detected"):
                await booter.download_file(
                    "../../etc/passwd", str(tmp_path / "out.txt")
                )

            # 4. Remote path outside workspace raises ValueError
            with pytest.raises(ValueError, match="Path outside workspace"):
                await booter.download_file("/etc/shadow", str(tmp_path / "out.txt"))

            # 5. HTTP 404 raises RuntimeError
            mock_session_404 = _MockClientSession(
                response=_MockResponse(status=404, text_data="File not found")
            )
            with patch("aiohttp.ClientSession", return_value=mock_session_404):
                with pytest.raises(RuntimeError, match="HTTP 404"):
                    await booter.download_file(
                        "missing.txt", str(tmp_path / "out.txt")
                    )

            # 6. Transport / client error is normalized to RuntimeError preserving cause
            conn_err = aiohttp.ClientConnectionError("Connection refused")
            mock_session_err = _MockClientSession(side_effect=conn_err)
            with patch("aiohttp.ClientSession", return_value=mock_session_err):
                with pytest.raises(RuntimeError, match="Failed to download file from sandbox") as exc_info:
                    await booter.download_file("file.txt", str(tmp_path / "out.txt"))
                assert exc_info.value.__cause__ is conn_err

            # 7. asyncio.TimeoutError is normalized to RuntimeError preserving cause
            timeout_err = asyncio.TimeoutError("Download timed out")
            mock_session_timeout = _MockClientSession(side_effect=timeout_err)
            with patch("aiohttp.ClientSession", return_value=mock_session_timeout):
                with pytest.raises(RuntimeError, match="Failed to download file from sandbox") as exc_info:
                    await booter.download_file("file.txt", str(tmp_path / "out.txt"))
                assert exc_info.value.__cause__ is timeout_err

            # 8. Unrelated programming error is not caught or converted
            with patch("aiohttp.ClientSession", side_effect=TypeError("programming error")):
                with pytest.raises(TypeError, match="programming error"):
                    await booter.download_file("file.txt", str(tmp_path / "out.txt"))

    @pytest.mark.asyncio
    async def test_shipyard_python_wrapper(self):
        """Test ShipyardPythonWrapper wraps flat output into standard data format."""
        mock_boxlite = MagicMock()
        with patch.dict(sys.modules, {"boxlite": mock_boxlite}):
            from astrbot.core.astr_agent_runtime.computer.booters.boxlite import (
                ShipyardPythonWrapper,
            )

            raw_python = MagicMock()

            # 1. Flat dictionary output from direct Ship microVM
            raw_python.exec = AsyncMock(
                return_value={
                    "success": True,
                    "output": {"text": "Hello Boxlite\n", "images": []},
                    "error": None,
                }
            )
            wrapper = ShipyardPythonWrapper(raw_python)
            res = await wrapper.exec("print('Hello Boxlite')")

            assert res["success"] is True
            assert res["data"]["output"]["text"] == "Hello Boxlite\n"
            assert res["data"]["error"] == ""
            assert res["output"] == "Hello Boxlite\n"

            # 2. Flat scalar output
            raw_python.exec = AsyncMock(
                return_value={
                    "success": True,
                    "output": "Scalar Result",
                    "error": "",
                }
            )
            res = await wrapper.exec("42")
            assert res["data"]["output"]["text"] == "Scalar Result"

            # 3. Silent execution suppresses output text
            res = await wrapper.exec("42", silent=True)
            assert res["data"]["output"]["text"] == ""

            # 4. Already wrapped response passed through
            wrapped_data = {"data": {"output": {"text": "prewrapped"}, "error": ""}}
            raw_python.exec = AsyncMock(return_value=wrapped_data)
            res = await wrapper.exec("test")
            assert res == wrapped_data

            # 5. Already wrapped response with silent=True suppresses text
            wrapped_with_text = {
                "success": True,
                "data": {"output": {"text": "should be suppressed", "images": []}, "error": ""},
                "output": "should be suppressed",
            }
            raw_python.exec = AsyncMock(return_value=wrapped_with_text)
            res_silent = await wrapper.exec("test", silent=True)
            assert res_silent["data"]["output"]["text"] == ""
            assert res_silent["output"] == ""

            # 6. Forward cwd parameter to underlying component
            raw_python.exec = AsyncMock(
                return_value={"success": True, "output": {"text": "ok", "images": []}}
            )
            await wrapper.exec("import os", cwd="/workspace/my_project")
            raw_python.exec.assert_awaited_with(
                code="import os",
                kernel_id=None,
                timeout=30,
                silent=False,
                cwd="/workspace/my_project",
            )

            # 7. Fallback when underlying component does not accept cwd
            async def _legacy_exec(code, kernel_id=None, timeout=30, silent=False):
                return {"success": True, "output": {"text": f"legacy: {code}"}}

            raw_python.exec = AsyncMock(side_effect=_legacy_exec)
            res_legacy = await wrapper.exec("test_legacy", cwd="/workspace/dir")
            assert res_legacy["data"]["output"]["text"] == "legacy: test_legacy"

            # 8. Unrelated TypeError is propagated immediately and called exactly once
            raw_python.exec = AsyncMock(
                side_effect=TypeError("unsupported operand type(s) for +: 'int' and 'str'")
            )
            with pytest.raises(TypeError, match="unsupported operand type"):
                await wrapper.exec("1 + '2'", cwd="/workspace/dir")
            assert raw_python.exec.call_count == 1

    @pytest.mark.asyncio
    async def test_python_tool_handle_result_flat_and_nested(self):
        """Test python computer tool handle_result accepts flat and nested formats."""
        from astrbot.core.astr_agent_runtime.tools.computer_tools.python import (
            handle_result,
        )

        event = MagicMock()
        event.get_platform_name.return_value = "terminal"

        # 1. Flat response format
        flat_res = {
            "output": {"text": "computed: 100", "images": []},
            "error": "",
        }
        tool_result = await handle_result(flat_res, event)
        assert len(tool_result.content) == 1
        assert tool_result.content[0].text == "computed: 100"

        # 2. Nested response format
        nested_res = {
            "data": {
                "output": {"text": "computed: 200", "images": []},
                "error": "",
            }
        }
        tool_result = await handle_result(nested_res, event)
        assert len(tool_result.content) == 1
        assert tool_result.content[0].text == "computed: 200"

        # 3. Empty output fallback
        empty_res = {"output": {"text": "", "images": []}, "error": ""}
        tool_result = await handle_result(empty_res, event)
        assert len(tool_result.content) == 1
        assert tool_result.content[0].text == "No output."

        # 4. Error response
        err_res = {"error": "NameError: name 'x' is not defined"}
        tool_result = await handle_result(err_res, event)
        assert any("error:" in c.text for c in tool_result.content)

        # 5. Top-level error preserved when data is populated without nested error
        mixed_res = {
            "success": False,
            "error": "Kernel terminated unexpectedly",
            "data": {
                "output": {"text": "partial calculations", "images": []},
            },
        }
        tool_result = await handle_result(mixed_res, event)
        assert any("error: Kernel terminated unexpectedly" in c.text for c in tool_result.content)
        assert any("partial calculations" in c.text for c in tool_result.content)

    @pytest.mark.asyncio
    async def test_file_read_utils_exec_python_json_flat_and_nested(self):
        """Test _exec_python_json in file_read_utils accepts flat and nested responses."""
        from astrbot.core.astr_agent_runtime.computer.file_read_utils import (
            _exec_python_json,
        )

        mock_booter = MagicMock()

        # 1. Flat response
        mock_booter.python.exec = AsyncMock(
            return_value={
                "output": {"text": json.dumps({"status": "ok", "value": 123})},
                "error": "",
            }
        )
        res = await _exec_python_json(mock_booter, "script", action="probe")
        assert res == {"status": "ok", "value": 123}

        # 2. Nested response
        mock_booter.python.exec = AsyncMock(
            return_value={
                "data": {
                    "output": {"text": json.dumps({"status": "ok", "value": 456})},
                    "error": "",
                }
            }
        )
        res = await _exec_python_json(mock_booter, "script", action="probe")
        assert res == {"status": "ok", "value": 456}

        # 3. Empty output raises RuntimeError
        mock_booter.python.exec = AsyncMock(
            return_value={"output": {"text": ""}, "error": ""}
        )
        with pytest.raises(RuntimeError, match="empty output"):
            await _exec_python_json(mock_booter, "script", action="probe")

    @pytest.mark.asyncio
    async def test_boxlite_lifecycle_capabilities_and_repeated_shutdown(self):
        """Test shutdown signature compatibility, capabilities lifecycle, and idempotent shutdown."""
        mock_boxlite = MagicMock()
        with patch.dict(sys.modules, {"boxlite": mock_boxlite}):
            from astrbot.core.astr_agent_runtime.computer.booters.boxlite import (
                BoxliteBooter,
                MockShipyardSandboxClient,
            )

            booter = BoxliteBooter()

            # 1. Capabilities before boot
            assert booter.capabilities is None

            # 2. Capabilities after boot (active mocked client)
            booter.mocked = MockShipyardSandboxClient("http://127.0.0.1:25000")
            assert booter.capabilities == ("python", "shell", "filesystem")

            # 3. Shutdown with arbitrary kwargs
            mock_box = MagicMock()
            mock_box.id = "ship-456"
            mock_box.shutdown = MagicMock()
            booter.box = mock_box

            await booter.shutdown(delete_sandbox=True, extra_param="ignored")
            assert booter._closed is True
            assert booter.box is None
            assert booter.mocked is None
            assert booter._python is None
            assert booter._shell is None
            assert booter._fs is None
            assert booter.capabilities is None
            mock_box.shutdown.assert_called_once()

            # 4. Repeated shutdown is safe and idempotent
            await booter.shutdown(delete_sandbox=True)
            assert booter._closed is True

            # 5. Boot after shutdown resets _closed and restores capabilities and availability
            reboot_box = MagicMock()
            reboot_box.id = "ship-reboot"
            reboot_box.start = AsyncMock()
            reboot_box.info.return_value = {"status": "running"}
            mock_boxlite.SimpleBox.return_value = reboot_box

            health_session = _MockClientSession(response=_MockResponse(status=200))
            with (
                patch("aiohttp.ClientSession", return_value=health_session),
                patch("asyncio.sleep", new_callable=AsyncMock),
            ):
                await booter.boot("reboot-sess")
                assert booter._closed is False
                assert booter.box is reboot_box
                assert booter.capabilities == ("python", "shell", "filesystem")
                assert await booter.available() is True

    @pytest.mark.asyncio
    async def test_boxlite_shutdown_failure_retains_references_and_retries(self):
        """Test shutdown failure raises RuntimeError, retains box reference, and allows retry."""
        mock_boxlite = MagicMock()
        with patch.dict(sys.modules, {"boxlite": mock_boxlite}):
            from astrbot.core.astr_agent_runtime.computer.booters.boxlite import (
                BoxliteBooter,
                MockShipyardSandboxClient,
            )

            booter = BoxliteBooter()
            mock_box = MagicMock()
            mock_box.id = "ship-fail"
            # 1. First shutdown attempt fails with an exception
            mock_box.shutdown.side_effect = RuntimeError("VM process stuck")
            booter.box = mock_box
            mocked_client = MockShipyardSandboxClient("http://127.0.0.1:25000")
            booter.mocked = mocked_client
            booter._python = MagicMock()
            booter._shell = MagicMock()
            booter._fs = MagicMock()

            with pytest.raises(
                RuntimeError, match="Failed to shutdown Boxlite sandbox ship-fail"
            ) as exc_info:
                await booter.shutdown()

            assert exc_info.value.__cause__ is not None
            # Crucially, references are retained when shutdown fails so cleanup can be retried
            assert booter.box is mock_box
            assert booter.mocked is mocked_client
            assert booter._python is not None
            assert booter._shell is not None
            assert booter._fs is not None

            # 2. Subsequent retry succeeds
            mock_box.shutdown.side_effect = None
            await booter.shutdown()

            assert booter._closed is True
            assert booter.box is None
            assert booter.mocked is None
            assert booter._python is None
            assert booter._shell is None
            assert booter._fs is None
            assert booter.capabilities is None

            # 3. Repeated call after successful shutdown is idempotent no-op
            await booter.shutdown()
            assert booter._closed is True

    @pytest.mark.asyncio
    async def test_boxlite_wait_healthy_retries_and_timeout(self):
        """Test wait_healthy succeeds on 200 after retries and raises TimeoutError on exhaustion."""
        mock_boxlite = MagicMock()
        with patch.dict(sys.modules, {"boxlite": mock_boxlite}):
            from astrbot.core.astr_agent_runtime.computer.booters.boxlite import (
                MockShipyardSandboxClient,
            )

            client = MockShipyardSandboxClient("http://127.0.0.1:25000", session_id="test-sess")

            # 1. Non-200 responses retry until status 200 arrives
            responses = [
                _MockResponse(status=503),
                _MockResponse(status=500),
                _MockResponse(status=200),
            ]
            mock_session = _MockClientSession(get_resp=responses)
            with (
                patch("aiohttp.ClientSession", return_value=mock_session),
                patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            ):
                await client.wait_healthy("ship-1", "sess-1")
                assert mock_sleep.await_count == 2

            # 2. Continual failure exhausts loop and raises TimeoutError
            fail_session = _MockClientSession(response=_MockResponse(status=500))
            with (
                patch("aiohttp.ClientSession", return_value=fail_session),
                patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            ):
                with pytest.raises(TimeoutError, match="failed to become healthy"):
                    await client.wait_healthy("ship-2", "sess-2")
                assert mock_sleep.await_count == 60


class TestComputerClient:
    """Tests for computer_client module functions."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("runtime", [None, "none", "local"])
    async def test_get_booter_requires_explicit_runtime(self, runtime):
        """An omitted runtime must not start or reuse a computer environment."""
        from astrbot.core.astr_agent_runtime.computer import computer_client

        provider_settings = {} if runtime is None else {"computer_use_runtime": runtime}
        context = MagicMock()
        context.get_config.return_value = {"provider_settings": provider_settings}
        with (
            patch.object(computer_client, "get_local_booter") as get_local_booter,
            patch.object(computer_client, "session_booter", {"session": MagicMock()}),
        ):
            if runtime == "local":
                result = await computer_client.get_booter(context, "session")
                assert result is get_local_booter.return_value
                get_local_booter.assert_called_once_with()
            else:
                with pytest.raises(RuntimeError, match="disabled by configuration"):
                    await computer_client.get_booter(context, "session")
                get_local_booter.assert_not_called()

    def test_get_local_booter(self):
        """Test get_local_booter returns singleton LocalBooter."""
        from astrbot.core.astr_agent_runtime.computer import computer_client

        # Clear the global booter to test singleton
        computer_client.local_booter = None

        booter1 = computer_client.get_local_booter()
        booter2 = computer_client.get_local_booter()

        assert isinstance(booter1, LocalBooter)
        assert booter1 is booter2  # Same instance (singleton)

        # Reset for other tests
        computer_client.local_booter = None

    @pytest.mark.asyncio
    async def test_shutdown_local_booter_clears_singleton(self):
        """Test local managed resources are released during lifecycle shutdown."""
        from astrbot.core.astr_agent_runtime.computer import computer_client

        booter = MagicMock(spec=LocalBooter)
        booter.shutdown = AsyncMock()
        computer_client.local_booter = booter

        await computer_client.shutdown_local_booter()

        booter.shutdown.assert_awaited_once()
        assert computer_client.local_booter is None

    @pytest.mark.asyncio
    async def test_get_booter_shipyard(self):
        """Test get_booter with shipyard type."""
        from astrbot.core.astr_agent_runtime.computer import computer_client
        from astrbot.core.astr_agent_runtime.computer.booters.shipyard import (
            ShipyardBooter,
        )

        # Clear session booter
        computer_client.session_booter.clear()

        mock_context = MagicMock()
        mock_config = MagicMock()
        mock_config.get = lambda key, default=None: {
            "provider_settings": {
                "computer_use_runtime": "sandbox",
                "sandbox": {
                    "booter": "shipyard",
                    "shipyard_endpoint": "http://localhost:8080",
                    "shipyard_access_token": "test_token",
                    "shipyard_ttl": 3600,
                    "shipyard_max_sessions": 10,
                },
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
                "astrbot.core.astr_agent_runtime.computer.computer_client._sync_skills_to_sandbox",
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
        from astrbot.core.astr_agent_runtime.computer import computer_client

        computer_client.session_booter.clear()

        mock_context = MagicMock()
        mock_config = MagicMock()
        mock_config.get = lambda key, default=None: {
            "provider_settings": {
                "computer_use_runtime": "sandbox",
                "sandbox": {
                    "booter": "unknown_type",
                },
            }
        }.get(key, default)
        mock_context.get_config = MagicMock(return_value=mock_config)

        with pytest.raises(ValueError) as exc_info:
            await computer_client.get_booter(mock_context, "test-session-id")
        assert "Unknown booter type" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_booter_reuses_existing(self):
        """Test get_booter reuses existing booter for same session."""
        from astrbot.core.astr_agent_runtime.computer import computer_client
        from astrbot.core.astr_agent_runtime.computer.booters.shipyard import (
            ShipyardBooter,
        )

        computer_client.session_booter.clear()

        mock_context = MagicMock()
        mock_config = MagicMock()
        mock_config.get = lambda key, default=None: {
            "provider_settings": {
                "computer_use_runtime": "sandbox",
                "sandbox": {
                    "booter": "shipyard",
                    "shipyard_endpoint": "http://localhost:8080",
                    "shipyard_access_token": "test_token",
                },
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
                "astrbot.core.astr_agent_runtime.computer.computer_client._sync_skills_to_sandbox",
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
        from astrbot.core.astr_agent_runtime.computer import computer_client
        from astrbot.core.astr_agent_runtime.computer.booters.shipyard import (
            ShipyardBooter,
        )

        computer_client.session_booter.clear()

        mock_context = MagicMock()
        mock_config = MagicMock()
        mock_config.get = lambda key, default=None: {
            "provider_settings": {
                "computer_use_runtime": "sandbox",
                "sandbox": {
                    "booter": "shipyard",
                    "shipyard_endpoint": "http://localhost:8080",
                    "shipyard_access_token": "test_token",
                },
            }
        }.get(key, default)
        mock_context.get_config = MagicMock(return_value=mock_config)

        mock_unavailable_booter = MagicMock(spec=ShipyardBooter)
        mock_unavailable_booter.available = AsyncMock(return_value=False)

        mock_new_booter = MagicMock(spec=ShipyardBooter)
        mock_new_booter.boot = AsyncMock()

        with (
            patch(
                "astrbot.core.astr_agent_runtime.computer.booters.shipyard.ShipyardBooter",
                return_value=mock_new_booter,
            ) as mock_booter_cls,
            patch(
                "astrbot.core.astr_agent_runtime.computer.computer_client._sync_skills_to_sandbox",
                AsyncMock(),
            ),
        ):
            session_id = "test-session-rebuild"
            # Pre-set the unavailable booter
            computer_client.session_booter[session_id] = mock_unavailable_booter

            # get_booter should detect the booter is unavailable and create a new one
            new_booter_instance = await computer_client.get_booter(
                mock_context, session_id
            )

            # Assert that a new booter was created and is now in the session
            mock_booter_cls.assert_called_once()
            mock_new_booter.boot.assert_awaited_once()
            assert new_booter_instance is mock_new_booter
            assert computer_client.session_booter[session_id] is mock_new_booter

        # Cleanup
        computer_client.session_booter.clear()


class TestSyncSkillsToSandbox:
    """Tests for _sync_skills_to_sandbox function."""

    @pytest.mark.asyncio
    async def test_sync_skills_no_skills_dir(self):
        """Test sync does nothing when skills directory doesn't exist."""
        from astrbot.core.astr_agent_runtime.computer import computer_client

        mock_booter = MagicMock()
        mock_booter.shell.exec = AsyncMock()
        mock_booter.upload_file = AsyncMock(return_value={"success": True})

        with (
            patch(
                "astrbot.core.astr_agent_runtime.computer.computer_client.get_astrbot_skills_path",
                return_value="/nonexistent/path",
            ),
            patch(
                "astrbot.core.astr_agent_runtime.computer.computer_client.os.path.isdir",
                return_value=False,
            ),
        ):
            await computer_client._sync_skills_to_sandbox(mock_booter)
            mock_booter.upload_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_skills_empty_dir(self):
        """Test sync does nothing when skills directory is empty."""
        from astrbot.core.astr_agent_runtime.computer import computer_client

        mock_booter = MagicMock()
        mock_booter.shell.exec = AsyncMock()
        mock_booter.upload_file = AsyncMock(return_value={"success": True})

        with (
            patch(
                "astrbot.core.astr_agent_runtime.computer.computer_client.get_astrbot_skills_path",
                return_value="/tmp/empty",
            ),
            patch(
                "astrbot.core.astr_agent_runtime.computer.computer_client.os.path.isdir",
                return_value=True,
            ),
            patch(
                "astrbot.core.astr_agent_runtime.computer.computer_client.Path.iterdir",
                return_value=iter([]),
            ),
        ):
            await computer_client._sync_skills_to_sandbox(mock_booter)
            mock_booter.upload_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_skills_success(self):
        """Test successful skills sync."""
        from astrbot.core.astr_agent_runtime.computer import computer_client

        mock_booter = MagicMock()
        mock_booter.shell.exec = AsyncMock(return_value={"exit_code": 0})
        mock_booter.upload_file = AsyncMock(return_value={"success": True})

        mock_skill_file = MagicMock()
        mock_skill_file.name = "skill.py"
        mock_skill_file.__str__ = lambda: "/tmp/skills/skill.py"

        with (
            patch(
                "astrbot.core.astr_agent_runtime.computer.computer_client.get_astrbot_skills_path",
                return_value="/tmp/skills",
            ),
            patch(
                "astrbot.core.astr_agent_runtime.computer.computer_client.os.path.isdir",
                return_value=True,
            ),
            patch(
                "astrbot.core.astr_agent_runtime.computer.computer_client.Path.iterdir",
                return_value=iter([mock_skill_file]),
            ),
            patch(
                "astrbot.core.astr_agent_runtime.computer.computer_client.get_astrbot_temp_path",
                return_value="/tmp",
            ),
            patch(
                "astrbot.core.astr_agent_runtime.computer.computer_client.shutil.make_archive",
            ),
            patch(
                "astrbot.core.astr_agent_runtime.computer.computer_client.os.path.exists",
                return_value=True,
            ),
            patch(
                "astrbot.core.astr_agent_runtime.computer.computer_client.os.remove",
            ),
        ):
            # Should not raise
            await computer_client._sync_skills_to_sandbox(mock_booter)
