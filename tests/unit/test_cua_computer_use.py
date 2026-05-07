import asyncio
import base64
import json
import shlex
from pathlib import Path

import mcp
import pytest

from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
from astrbot.core.config.default import CONFIG_METADATA_3
from astrbot.core.provider.func_tool_manager import FunctionToolManager


class FakeContext:
    def __init__(self, config: dict):
        self._config = config

    def get_config(self, umo: str | None = None):
        return self._config


class FakeShell:
    def __init__(self):
        self.commands = []

    async def run(self, command: str, **kwargs):
        self.commands.append((command, kwargs))
        return {"stdout": "ok", "stderr": "", "exit_code": 0}


class ProcessShapeShell:
    async def run(self, command: str, **kwargs):
        return {"output": "shape-ok", "returncode": 0}


class CommandResultShapeShell:
    def __init__(self, stdout: str = "shape-ok", stderr: str = "", returncode: int = 0):
        self.commands = []
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode

    @property
    def success(self):
        return self.returncode == 0

    async def run(self, command: str, **kwargs):
        self.commands.append((command, kwargs))
        return self


class FakePython:
    async def run(self, code: str, **kwargs):
        return {"output": "42", "error": ""}


class FakeFilesystem:
    def __init__(self):
        self.files = {}

    async def write_file(self, path: str, content: str):
        self.files[path] = content

    async def read_file(self, path: str):
        return self.files[path]

    async def delete(self, path: str):
        self.files.pop(path, None)

    async def list_dir(self, path: str):
        return [path]


class FakeFiles:
    def __init__(self):
        self.uploads = []
        self.byte_writes = []
        self.text_writes = []
        self.text_reads = {}

    async def upload(self, local_path: str, remote_path: str):
        self.uploads.append((local_path, remote_path))

    async def write_bytes(self, path: str, content: bytes):
        self.byte_writes.append((path, content))

    async def write_text(self, path: str, content: str):
        self.text_writes.append((path, content))
        self.text_reads[path] = content

    async def read_text(self, path: str):
        return self.text_reads[path]


class FakeMouse:
    def __init__(self):
        self.clicks = []

    async def click(self, x: int, y: int, button: str = "left"):
        self.clicks.append((x, y, button))
        return {"success": True}


class FakeKeyboard:
    def __init__(self):
        self.typed = []
        self.pressed = []

    async def type(self, text: str):
        self.typed.append(text)
        return {"success": True}

    async def press(self, key: str):
        self.pressed.append(key)
        return {"success": True}


class FakeSandbox:
    def __init__(self):
        self.shell = FakeShell()
        self.python = FakePython()
        self.filesystem = FakeFilesystem()
        self.mouse = FakeMouse()
        self.keyboard = FakeKeyboard()

    async def screenshot(self):
        return b"fake-png"


class SyncShell:
    def __init__(self, stdout: str = "ok"):
        self.commands = []
        self.stdout = stdout

    def run(self, command: str, **kwargs):
        self.commands.append((command, kwargs))
        return {"stdout": self.stdout, "stderr": "", "exit_code": 0}


class FailingShell:
    def __init__(self):
        self.commands = []

    async def run(self, command: str, **kwargs):
        self.commands.append((command, kwargs))
        return {
            "stdout": "",
            "stderr": "python3: command not found",
            "exit_code": 127,
            "success": False,
        }


class SandboxWithoutFilesystem:
    def __init__(self):
        self.shell = FakeShell()
        self.python = FakePython()


class SyncPython:
    def run(self, code: str, **kwargs):
        return {"output": "sync", "error": ""}


def _agent_computer_use_items():
    return CONFIG_METADATA_3["ai_group"]["metadata"]["agent_computer_use"]["items"]


@pytest.mark.asyncio
async def test_get_booter_creates_cua_booter(monkeypatch):
    from astrbot.core.computer import computer_client

    created = []

    class FakeCuaBooter:
        def __init__(
            self,
            image: str,
            os_type: str,
            ttl: int,
            telemetry_enabled: bool,
            local: bool,
            api_key: str,
        ):
            created.append((image, os_type, ttl, telemetry_enabled, local, api_key))

        async def boot(self, session_id: str):
            self.session_id = session_id

        async def available(self):
            return True

    monkeypatch.setattr(
        computer_client, "_sync_skills_to_sandbox", lambda booter: asyncio.sleep(0)
    )
    monkeypatch.setitem(computer_client.session_booter, "cua-test", None)
    computer_client.session_booter.pop("cua-test", None)
    monkeypatch.setattr(
        "astrbot.core.computer.booters.cua.CuaBooter",
        FakeCuaBooter,
        raising=False,
    )

    ctx = FakeContext(
        {
            "provider_settings": {
                "computer_use_runtime": "sandbox",
                "sandbox": {
                    "booter": "cua",
                    "cua_image": "linux",
                    "cua_os_type": "linux",
                    "cua_ttl": 120,
                    "cua_telemetry_enabled": False,
                    "cua_local": True,
                    "cua_api_key": "",
                },
            }
        }
    )

    booter = await computer_client.get_booter(ctx, "cua-test")

    assert isinstance(booter, FakeCuaBooter)
    assert created == [("linux", "linux", 120, False, True, "")]


def test_cua_ephemeral_kwargs_include_local_when_supported():
    from astrbot.core.computer.booters.cua import CuaBooter

    def ephemeral(image, ttl=None, telemetry_enabled=None, local=None):
        return image, ttl, telemetry_enabled, local

    kwargs = CuaBooter(
        ttl=120, telemetry_enabled=False, local=True
    )._build_ephemeral_kwargs(ephemeral)

    assert kwargs == {"ttl": 120, "telemetry_enabled": False, "local": True}


def test_cua_ephemeral_kwargs_include_api_key_for_cloud_when_supported():
    from astrbot.core.computer.booters.cua import CuaBooter

    def ephemeral(image, local=None, api_key=None):
        return image, local, api_key

    kwargs = CuaBooter(local=False, api_key="sk-test")._build_ephemeral_kwargs(
        ephemeral
    )

    assert kwargs == {"local": False, "api_key": "sk-test"}


def test_cua_default_config_matches_booter_defaults():
    from astrbot.core.computer.booters.cua import CUA_DEFAULT_CONFIG, CuaBooter
    from astrbot.core.config.default import DEFAULT_CONFIG

    booter = CuaBooter()
    sandbox_defaults = DEFAULT_CONFIG["provider_settings"]["sandbox"]

    assert booter.image == CUA_DEFAULT_CONFIG["image"]
    assert booter.os_type == CUA_DEFAULT_CONFIG["os_type"]
    assert booter.ttl == CUA_DEFAULT_CONFIG["ttl"]
    assert booter.telemetry_enabled == CUA_DEFAULT_CONFIG["telemetry_enabled"]
    assert booter.local == CUA_DEFAULT_CONFIG["local"]
    assert booter.api_key == CUA_DEFAULT_CONFIG["api_key"]
    assert sandbox_defaults["cua_image"] == CUA_DEFAULT_CONFIG["image"]
    assert sandbox_defaults["cua_os_type"] == CUA_DEFAULT_CONFIG["os_type"]
    assert sandbox_defaults["cua_ttl"] == CUA_DEFAULT_CONFIG["ttl"]
    assert (
        sandbox_defaults["cua_telemetry_enabled"]
        == CUA_DEFAULT_CONFIG["telemetry_enabled"]
    )
    assert sandbox_defaults["cua_local"] == CUA_DEFAULT_CONFIG["local"]
    assert sandbox_defaults["cua_api_key"] == CUA_DEFAULT_CONFIG["api_key"]


@pytest.mark.asyncio
async def test_cua_config_log_does_not_include_api_key(monkeypatch):
    from astrbot.core.computer import computer_client

    log_messages = []

    class FakeCuaBooter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def boot(self, session_id: str):
            self.session_id = session_id

        async def available(self):
            return True

    monkeypatch.setattr(
        computer_client, "_sync_skills_to_sandbox", lambda booter: asyncio.sleep(0)
    )
    monkeypatch.setitem(computer_client.session_booter, "cua-log-test", None)
    computer_client.session_booter.pop("cua-log-test", None)
    monkeypatch.setattr(
        "astrbot.core.computer.booters.cua.CuaBooter",
        FakeCuaBooter,
        raising=False,
    )
    monkeypatch.setattr(computer_client.logger, "info", log_messages.append)

    ctx = FakeContext(
        {
            "provider_settings": {
                "computer_use_runtime": "sandbox",
                "sandbox": {
                    "booter": "cua",
                    "cua_local": False,
                    "cua_api_key": "sk-secret-value",
                },
            }
        }
    )

    await computer_client.get_booter(ctx, "cua-log-test")

    assert log_messages
    assert all("sk-secret-value" not in message for message in log_messages)
    assert all("api_key" not in message for message in log_messages)


@pytest.mark.asyncio
async def test_get_booter_shuts_down_client_when_skill_sync_fails(monkeypatch):
    from astrbot.core.computer import computer_client

    shutdowns = []

    class FakeCuaBooter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def boot(self, session_id: str):
            self.session_id = session_id

        async def shutdown(self):
            shutdowns.append(self.session_id)

    async def fail_sync(booter):
        raise RuntimeError("sync failed")

    monkeypatch.setattr(computer_client, "_sync_skills_to_sandbox", fail_sync)
    monkeypatch.setitem(computer_client.session_booter, "cua-sync-fail", None)
    computer_client.session_booter.pop("cua-sync-fail", None)
    monkeypatch.setattr(
        "astrbot.core.computer.booters.cua.CuaBooter",
        FakeCuaBooter,
        raising=False,
    )

    ctx = FakeContext(
        {
            "provider_settings": {
                "computer_use_runtime": "sandbox",
                "sandbox": {"booter": "cua"},
            }
        }
    )

    with pytest.raises(RuntimeError, match="sync failed"):
        await computer_client.get_booter(ctx, "cua-sync-fail")

    assert len(shutdowns) == 1
    assert "cua-sync-fail" not in computer_client.session_booter


@pytest.mark.asyncio
async def test_cua_components_map_sdk_results(tmp_path):
    from astrbot.core.computer.booters.cua import (
        CuaFileSystemComponent,
        CuaGUIComponent,
        CuaPythonComponent,
        CuaShellComponent,
    )

    sandbox = FakeSandbox()

    shell_result = await CuaShellComponent(sandbox).exec("echo ok", cwd="/workspace")
    python_result = await CuaPythonComponent(sandbox).exec("print(42)")
    fs = CuaFileSystemComponent(sandbox)
    await fs.write_file("hello.txt", "hello")
    read_result = await fs.read_file("hello.txt")
    screenshot_path = tmp_path / "screen.png"
    gui = CuaGUIComponent(sandbox)
    screenshot_result = await gui.screenshot(str(screenshot_path))
    click_result = await gui.click(10, 20, button="right")
    type_result = await gui.type_text("hello")
    press_result = await gui.press_key("Enter")

    assert shell_result["stdout"] == "ok"
    assert python_result["data"]["output"]["text"] == "42"
    assert read_result["content"] == "hello"
    assert screenshot_path.read_bytes() == b"fake-png"
    assert screenshot_result["mime_type"] == "image/png"
    assert click_result["success"] is True
    assert type_result["success"] is True
    assert press_result["success"] is True
    assert sandbox.mouse.clicks == [(10, 20, "right")]
    assert sandbox.keyboard.typed == ["hello"]
    assert sandbox.keyboard.pressed == ["Enter"]


@pytest.mark.asyncio
async def test_cua_list_dir_returns_entries_list_for_shell_fallback():
    from astrbot.core.computer.booters.cua import CuaFileSystemComponent

    sandbox = FakeSandbox()
    delattr(sandbox, "filesystem")

    result = await CuaFileSystemComponent(sandbox).list_dir(".")

    assert result["success"] is True
    assert result["entries"] == ["ok"]
    assert sandbox.shell.commands[0][0] == "ls -1 ."


@pytest.mark.asyncio
async def test_cua_shell_filesystem_fallback_shell_quotes_paths():
    from astrbot.core.computer.booters.cua import CuaFileSystemComponent

    path = "folder/it's file.txt"
    sandbox = FakeSandbox()
    delattr(sandbox, "filesystem")
    fs = CuaFileSystemComponent(sandbox)

    await fs.read_file(path)
    await fs.delete_file(path)
    await fs.list_dir(path)

    assert sandbox.shell.commands[0][0] == f"cat {shlex.quote(path)}"
    assert sandbox.shell.commands[1][0] == f"rm -rf {shlex.quote(path)}"
    assert sandbox.shell.commands[2][0] == f"ls -1 {shlex.quote(path)}"


@pytest.mark.asyncio
async def test_cua_write_file_shell_fallback_uses_python_base64_decoder():
    from astrbot.core.computer.booters.cua import CuaFileSystemComponent

    sandbox = FakeSandbox()
    delattr(sandbox, "filesystem")

    await CuaFileSystemComponent(sandbox).write_file("hello.txt", "hello")

    command = sandbox.shell.commands[0][0]
    assert "python3 -c" in command
    assert "base64 -d" not in command


@pytest.mark.asyncio
async def test_cua_create_file_reports_mode_as_informational():
    from astrbot.core.computer.booters.cua import CuaFileSystemComponent

    sandbox = FakeSandbox()

    result = await CuaFileSystemComponent(sandbox).create_file("hello.txt", mode=0o600)

    assert result["success"] is True
    assert result["mode"] == 0o600
    assert result["mode_applied"] is False


@pytest.mark.asyncio
async def test_cua_write_file_shell_fallback_propagates_shell_failure():
    from astrbot.core.computer.booters.cua import CuaFileSystemComponent

    sandbox = FakeSandbox()
    sandbox.shell = FailingShell()
    delattr(sandbox, "filesystem")

    result = await CuaFileSystemComponent(sandbox).write_file("hello.txt", "hello")

    assert result["success"] is False
    assert "requires python3" in result["stderr"]
    assert "python3: command not found" in result["stderr"]
    assert result["path"] == "hello.txt"


@pytest.mark.asyncio
async def test_cua_edit_file_propagates_write_failure():
    from astrbot.core.computer.booters.cua import CuaFileSystemComponent

    class ReadableButFailingWriteShell:
        def __init__(self):
            self.commands = []

        async def run(self, command: str, **kwargs):
            self.commands.append((command, kwargs))
            if command.startswith("cat "):
                return {"stdout": "hello old", "stderr": "", "exit_code": 0}
            return {
                "stdout": "",
                "stderr": "permission denied",
                "exit_code": 1,
                "success": False,
            }

    sandbox = FakeSandbox()
    sandbox.shell = ReadableButFailingWriteShell()
    delattr(sandbox, "filesystem")

    result = await CuaFileSystemComponent(sandbox).edit_file("hello.txt", "old", "new")

    assert result["success"] is False
    assert result["stderr"] == "permission denied"
    assert result["path"] == "hello.txt"


@pytest.mark.asyncio
async def test_cua_list_dir_shell_fallback_returns_filename_only_entries():
    from astrbot.core.computer.booters.cua import CuaFileSystemComponent

    sandbox = FakeSandbox()
    sandbox.shell = SyncShell("alpha.txt\nfolder\n")
    delattr(sandbox, "filesystem")

    result = await CuaFileSystemComponent(sandbox).list_dir(".", show_hidden=True)

    assert result["entries"] == ["alpha.txt", "folder"]
    assert sandbox.shell.commands[0][0] == "ls -1A ."


@pytest.mark.asyncio
async def test_cua_shell_filesystem_fallback_rejects_non_posix_os_type():
    from astrbot.core.computer.booters.cua import CuaFileSystemComponent

    sandbox = SandboxWithoutFilesystem()
    fs = CuaFileSystemComponent(sandbox, os_type="windows")

    read_result = await fs.read_file("hello.txt")
    write_result = await fs.write_file("hello.txt", "hello")
    delete_result = await fs.delete_file("hello.txt")
    list_result = await fs.list_dir(".")

    for result in (read_result, write_result, delete_result, list_result):
        assert result["success"] is False
        assert (
            "filesystem shell fallback is only supported for POSIX" in result["error"]
        )
    assert sandbox.shell.commands == []


@pytest.mark.asyncio
async def test_cua_shell_and_python_accept_sync_sdk_methods():
    from astrbot.core.computer.booters.cua import CuaPythonComponent, CuaShellComponent

    sandbox = FakeSandbox()
    sandbox.shell = SyncShell()
    sandbox.python = SyncPython()

    shell_result = await CuaShellComponent(sandbox).exec("echo ok")
    python_result = await CuaPythonComponent(sandbox).exec("print('ok')")

    assert shell_result["stdout"] == "ok"
    assert python_result["data"]["output"]["text"] == "sync"


@pytest.mark.asyncio
async def test_cua_filesystem_prefers_native_files_interface():
    from astrbot.core.computer.booters.cua import CuaFileSystemComponent

    sandbox = SandboxWithoutFilesystem()
    sandbox.files = FakeFiles()

    fs = CuaFileSystemComponent(sandbox)
    await fs.write_file("hello.txt", "hello")
    result = await fs.read_file("hello.txt")

    assert sandbox.files.text_writes == [("hello.txt", "hello")]
    assert result["success"] is True
    assert result["content"] == "hello"
    assert sandbox.shell.commands == []


@pytest.mark.asyncio
async def test_cua_filesystem_uses_legacy_filesystem_when_files_lacks_method():
    from astrbot.core.computer.booters.cua import CuaFileSystemComponent

    sandbox = SandboxWithoutFilesystem()
    sandbox.files = type("UploadOnlyFiles", (), {"upload": FakeFiles().upload})()
    sandbox.filesystem = FakeFilesystem()

    fs = CuaFileSystemComponent(sandbox)
    await fs.write_file("hello.txt", "hello")
    result = await fs.read_file("hello.txt")

    assert sandbox.filesystem.files == {"hello.txt": "hello"}
    assert result["success"] is True
    assert result["content"] == "hello"
    assert sandbox.shell.commands == []


@pytest.mark.asyncio
async def test_cua_shell_normalizes_output_returncode_shape():
    from astrbot.core.computer.booters.cua import CuaShellComponent

    sandbox = FakeSandbox()
    sandbox.shell = ProcessShapeShell()

    result = await CuaShellComponent(sandbox).exec("echo ok")

    assert result == {
        "stdout": "shape-ok",
        "stderr": "",
        "exit_code": 0,
        "success": True,
    }


@pytest.mark.asyncio
async def test_cua_shell_normalizes_command_result_object_shape():
    from astrbot.core.computer.booters.cua import CuaShellComponent

    sandbox = FakeSandbox()
    sandbox.shell = CommandResultShapeShell(stdout="hello\n", returncode=0)

    result = await CuaShellComponent(sandbox).exec("echo hello")

    assert result == {
        "stdout": "hello\n",
        "stderr": "",
        "exit_code": 0,
        "success": True,
    }


@pytest.mark.asyncio
async def test_cua_shell_prefers_returncode_when_exit_code_is_none():
    from astrbot.core.computer.booters.cua import CuaShellComponent

    class ShellWithMixedExitCode:
        async def run(self, command: str, **kwargs):
            return {
                "stdout": "",
                "stderr": "",
                "exit_code": None,
                "returncode": 1,
            }

    sandbox = FakeSandbox()
    sandbox.shell = ShellWithMixedExitCode()

    result = await CuaShellComponent(sandbox).exec("false")

    assert result["exit_code"] == 1
    assert result["success"] is False


@pytest.mark.asyncio
async def test_cua_python_fallback_preserves_shell_command_result_stdout():
    from astrbot.core.computer.booters.cua import CuaPythonComponent

    sandbox = SandboxWithoutFilesystem()
    sandbox.shell = CommandResultShapeShell(stdout="from python fallback\n")
    delattr(sandbox, "python")

    result = await CuaPythonComponent(sandbox).exec("print('from python fallback')")

    assert result["success"] is True
    assert result["output"] == "from python fallback\n"
    assert result["data"]["output"]["text"] == "from python fallback\n"


@pytest.mark.asyncio
async def test_cua_shell_background_wrapper_detaches_via_python_subprocess():
    from astrbot.core.computer.booters.cua import CuaShellComponent

    sandbox = FakeSandbox()

    await CuaShellComponent(sandbox).exec(
        "chromium https://example.com", background=True
    )

    command = sandbox.shell.commands[0][0]
    assert command.startswith("python3 -c ")
    assert "subprocess.Popen" in command
    assert "start_new_session=True" in command
    assert "p.pid" in command
    assert "stdout=subprocess.DEVNULL" in command
    assert "stderr=subprocess.DEVNULL" in command
    assert "time.sleep(0.2)" in command
    assert "'chromium https://example.com'" in command
    assert "&" not in command


@pytest.mark.asyncio
async def test_cua_shell_background_rejects_non_posix_os_type():
    from astrbot.core.computer.booters.cua import CuaShellComponent

    sandbox = FakeSandbox()

    result = await CuaShellComponent(sandbox, os_type="windows").exec(
        "start notepad", background=True
    )

    assert result == {
        "stdout": "",
        "stderr": "error: background shell execution is only supported for POSIX CUA images.",
        "exit_code": 2,
        "success": False,
    }
    assert sandbox.shell.commands == []


@pytest.mark.asyncio
async def test_cua_upload_file_fallback_rejects_non_posix_os_type(tmp_path):
    from astrbot.core.computer.booters.cua import (
        CuaBooter,
        CuaFileSystemComponent,
        CuaGUIComponent,
        CuaPythonComponent,
        CuaShellComponent,
        _CuaRuntime,
    )

    local_file = tmp_path / "upload.txt"
    local_file.write_text("hello", encoding="utf-8")
    sandbox = SandboxWithoutFilesystem()
    booter = CuaBooter(os_type="windows")
    booter._runtime = _CuaRuntime(
        sandbox_cm=object(),
        sandbox=sandbox,
        shell=CuaShellComponent(sandbox, os_type="windows"),
        python=CuaPythonComponent(sandbox, os_type="windows"),
        fs=CuaFileSystemComponent(sandbox, os_type="windows"),
        gui=CuaGUIComponent(sandbox),
    )

    result = await booter.upload_file(str(local_file), "remote.txt")

    assert result["success"] is False
    assert "filesystem shell fallback is only supported for POSIX" in result["error"]
    assert sandbox.shell.commands == []


@pytest.mark.asyncio
async def test_cua_upload_file_prefers_native_files_upload(tmp_path):
    from astrbot.core.computer.booters.cua import (
        CuaBooter,
        CuaFileSystemComponent,
        CuaGUIComponent,
        CuaPythonComponent,
        CuaShellComponent,
        _CuaRuntime,
    )

    local_file = tmp_path / "upload.txt"
    local_file.write_text("hello", encoding="utf-8")
    sandbox = SandboxWithoutFilesystem()
    sandbox.files = FakeFiles()
    booter = CuaBooter()
    booter._runtime = _CuaRuntime(
        sandbox_cm=object(),
        sandbox=sandbox,
        shell=CuaShellComponent(sandbox),
        python=CuaPythonComponent(sandbox),
        fs=CuaFileSystemComponent(sandbox),
        gui=CuaGUIComponent(sandbox),
    )

    result = await booter.upload_file(str(local_file), "remote.txt")

    assert result["success"] is True
    assert sandbox.files.uploads == [(str(local_file), "remote.txt")]
    assert sandbox.shell.commands == []


@pytest.mark.asyncio
async def test_cua_upload_file_uses_native_write_bytes_when_upload_missing(tmp_path):
    from astrbot.core.computer.booters.cua import (
        CuaBooter,
        CuaFileSystemComponent,
        CuaGUIComponent,
        CuaPythonComponent,
        CuaShellComponent,
        _CuaRuntime,
    )

    class FilesWithoutUpload:
        def __init__(self):
            self.byte_writes = []

        async def write_bytes(self, path: str, content: bytes):
            self.byte_writes.append((path, content))

    local_file = tmp_path / "upload.txt"
    local_file.write_bytes(b"hello-bytes")
    sandbox = SandboxWithoutFilesystem()
    sandbox.files = FilesWithoutUpload()
    booter = CuaBooter()
    booter._runtime = _CuaRuntime(
        sandbox_cm=object(),
        sandbox=sandbox,
        shell=CuaShellComponent(sandbox),
        python=CuaPythonComponent(sandbox),
        fs=CuaFileSystemComponent(sandbox),
        gui=CuaGUIComponent(sandbox),
    )

    result = await booter.upload_file(str(local_file), "remote.txt")

    assert result["success"] is True
    assert sandbox.files.byte_writes == [("remote.txt", b"hello-bytes")]
    assert sandbox.shell.commands == []


@pytest.mark.asyncio
async def test_cua_upload_file_propagates_native_upload_failure_result(tmp_path):
    from astrbot.core.computer.booters.cua import (
        CuaBooter,
        CuaFileSystemComponent,
        CuaGUIComponent,
        CuaPythonComponent,
        CuaShellComponent,
        _CuaRuntime,
    )

    class FailingFilesUpload:
        async def upload(self, local_path: str, remote_path: str):
            return {"success": False, "error": "disk full"}

    local_file = tmp_path / "upload.txt"
    local_file.write_text("hello", encoding="utf-8")
    sandbox = SandboxWithoutFilesystem()
    sandbox.files = FailingFilesUpload()
    booter = CuaBooter()
    booter._runtime = _CuaRuntime(
        sandbox_cm=object(),
        sandbox=sandbox,
        shell=CuaShellComponent(sandbox),
        python=CuaPythonComponent(sandbox),
        fs=CuaFileSystemComponent(sandbox),
        gui=CuaGUIComponent(sandbox),
    )

    result = await booter.upload_file(str(local_file), "remote.txt")

    assert result["success"] is False
    assert result["error"] == "disk full"


@pytest.mark.asyncio
async def test_cua_download_file_shell_quotes_remote_path(tmp_path):
    from astrbot.core.computer.booters.cua import (
        CuaBooter,
        CuaFileSystemComponent,
        CuaGUIComponent,
        CuaPythonComponent,
        CuaShellComponent,
        _CuaRuntime,
    )

    class Base64Shell(FakeShell):
        async def run(self, command: str, **kwargs):
            self.commands.append((command, kwargs))
            return {
                "stdout": base64.b64encode(b"hello").decode(),
                "stderr": "",
                "exit_code": 0,
            }

    sandbox = SandboxWithoutFilesystem()
    sandbox.shell = Base64Shell()
    booter = CuaBooter()
    booter._runtime = _CuaRuntime(
        sandbox_cm=object(),
        sandbox=sandbox,
        shell=CuaShellComponent(sandbox),
        python=CuaPythonComponent(sandbox),
        fs=CuaFileSystemComponent(sandbox),
        gui=CuaGUIComponent(sandbox),
    )
    remote_path = "folder/it's file.txt"
    local_path = tmp_path / "download.txt"

    await booter.download_file(remote_path, str(local_path))

    assert sandbox.shell.commands[0][0] == f"base64 {shlex.quote(remote_path)}"
    assert local_path.read_bytes() == b"hello"


@pytest.mark.asyncio
async def test_cua_download_file_fallback_rejects_non_posix_os_type(tmp_path):
    from astrbot.core.computer.booters.cua import (
        CuaBooter,
        CuaFileSystemComponent,
        CuaGUIComponent,
        CuaPythonComponent,
        CuaShellComponent,
        _CuaRuntime,
    )

    sandbox = SandboxWithoutFilesystem()
    booter = CuaBooter(os_type="windows")
    booter._runtime = _CuaRuntime(
        sandbox_cm=object(),
        sandbox=sandbox,
        shell=CuaShellComponent(sandbox, os_type="windows"),
        python=CuaPythonComponent(sandbox, os_type="windows"),
        fs=CuaFileSystemComponent(sandbox, os_type="windows"),
        gui=CuaGUIComponent(sandbox),
    )

    with pytest.raises(RuntimeError, match="filesystem shell fallback"):
        await booter.download_file("remote.txt", str(tmp_path / "download.txt"))

    assert sandbox.shell.commands == []


@pytest.mark.asyncio
async def test_cua_boot_cleans_up_sandbox_when_component_setup_fails(monkeypatch):
    from astrbot.core.computer.booters import cua as cua_booter

    closed = []

    class FakeSandboxContext:
        async def __aenter__(self):
            return FakeSandbox()

        async def __aexit__(self, exc_type, exc, tb):
            closed.append((exc_type, exc, tb))

    class FakeImage:
        @staticmethod
        def linux():
            return "linux-image"

    class FakeSandboxFactory:
        @staticmethod
        def ephemeral(image, **kwargs):
            return FakeSandboxContext()

    class BrokenShellComponent:
        def __init__(self, sandbox, os_type="linux"):
            raise RuntimeError("component setup failed")

    original_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "cua":

            class FakeCuaModule:
                Image = FakeImage
                Sandbox = FakeSandboxFactory

            return FakeCuaModule()
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)
    monkeypatch.setattr(cua_booter, "CuaShellComponent", BrokenShellComponent)

    booter = cua_booter.CuaBooter()

    with pytest.raises(RuntimeError, match="component setup failed"):
        await booter.boot("session")

    assert len(closed) == 1
    assert booter._runtime is None


@pytest.mark.asyncio
async def test_cua_shell_background_reports_missing_python3_requirement():
    from astrbot.core.computer.booters.cua import CuaShellComponent

    sandbox = FakeSandbox()
    sandbox.shell = FailingShell()

    result = await CuaShellComponent(sandbox).exec("firefox", background=True)

    assert result["success"] is False
    assert "requires python3" in result["stderr"]
    assert "python3: command not found" in result["stderr"]


@pytest.mark.asyncio
async def test_cua_python_fallback_reports_missing_python3_requirement():
    from astrbot.core.computer.booters.cua import CuaPythonComponent

    sandbox = SandboxWithoutFilesystem()
    sandbox.shell = FailingShell()
    delattr(sandbox, "python")

    result = await CuaPythonComponent(sandbox).exec("print('hello')")

    assert result["success"] is False
    assert "requires python3" in result["error"]
    assert "python3: command not found" in result["error"]


@pytest.mark.asyncio
async def test_cua_gui_reports_missing_mouse_or_keyboard():
    from astrbot.core.computer.booters.cua import CuaGUIComponent

    class SandboxWithoutGuiDevices:
        async def screenshot(self):
            return b"fake-png"

    gui = CuaGUIComponent(SandboxWithoutGuiDevices())

    with pytest.raises(RuntimeError, match="mouse.*click"):
        await gui.click(1, 2)

    with pytest.raises(RuntimeError, match="keyboard.*type"):
        await gui.type_text("hello")

    with pytest.raises(RuntimeError, match="keyboard.*press"):
        await gui.press_key("Enter")


@pytest.mark.asyncio
async def test_cua_gui_press_error_lists_probed_methods():
    from astrbot.core.computer.booters.cua import CuaGUIComponent

    class SandboxWithoutPress:
        keyboard = object()

    gui = CuaGUIComponent(SandboxWithoutPress())

    with pytest.raises(RuntimeError) as exc_info:
        await gui.press_key("Enter")

    message = str(exc_info.value)
    assert "keyboard.press" in message
    assert "keyboard.key_press" in message
    assert "keyboard.press_key" in message


@pytest.mark.asyncio
async def test_cua_gui_caches_component_methods_after_initialization():
    from astrbot.core.computer.booters.cua import CuaGUIComponent

    class CountingMouse:
        def __init__(self):
            self.click_lookups = 0
            self.clicks = []

        def __getattribute__(self, name):
            if name == "click":
                object.__getattribute__(self, "__dict__")["click_lookups"] += 1
            return object.__getattribute__(self, name)

        async def click(self, x: int, y: int, button: str = "left"):
            self.clicks.append((x, y, button))
            return {"success": True}

    class Sandbox:
        def __init__(self):
            self.mouse = CountingMouse()

    sandbox = Sandbox()
    gui = CuaGUIComponent(sandbox)

    await gui.click(1, 2)
    await gui.click(3, 4, button="right")

    assert sandbox.mouse.click_lookups == 1
    assert sandbox.mouse.clicks == [(1, 2, "left"), (3, 4, "right")]


def test_cua_capabilities_reflect_initialized_sandbox_gui_devices():
    from astrbot.core.computer.booters.cua import (
        CuaBooter,
        CuaFileSystemComponent,
        CuaGUIComponent,
        CuaPythonComponent,
        CuaShellComponent,
        _CuaRuntime,
    )

    def set_runtime(booter, sandbox):
        shell = CuaShellComponent(sandbox)
        booter._runtime = _CuaRuntime(
            sandbox_cm=object(),
            sandbox=sandbox,
            shell=shell,
            python=CuaPythonComponent(sandbox),
            fs=CuaFileSystemComponent(sandbox),
            gui=CuaGUIComponent(sandbox),
        )

    booter = CuaBooter()
    set_runtime(booter, FakeSandbox())

    assert booter.capabilities == (
        "python",
        "shell",
        "filesystem",
        "gui",
        "screenshot",
        "mouse",
        "keyboard",
    )

    class ScreenshotOnlySandbox:
        shell = FakeShell()

        async def screenshot(self):
            return b"fake-png"

    set_runtime(booter, ScreenshotOnlySandbox())

    assert booter.capabilities == ("python", "shell", "filesystem", "gui", "screenshot")


@pytest.mark.asyncio
async def test_cua_shutdown_clears_cached_components():
    from astrbot.core.computer.booters.cua import (
        CuaBooter,
        CuaFileSystemComponent,
        CuaGUIComponent,
        CuaPythonComponent,
        CuaShellComponent,
        _CuaRuntime,
    )

    closed = []

    class FakeSandboxContext:
        async def __aexit__(self, exc_type, exc, tb):
            closed.append(True)

    booter = CuaBooter()
    sandbox = FakeSandbox()
    booter._runtime = _CuaRuntime(
        sandbox_cm=FakeSandboxContext(),
        sandbox=sandbox,
        shell=CuaShellComponent(sandbox),
        python=CuaPythonComponent(sandbox),
        fs=CuaFileSystemComponent(sandbox),
        gui=CuaGUIComponent(sandbox),
    )

    await booter.shutdown()

    assert closed == [True]
    assert await booter.available() is False
    assert booter._runtime is None


def test_cua_tools_are_registered_as_builtin_tools():
    from astrbot.core.tools.computer_tools.cua import (
        CuaKeyboardTypeTool,
        CuaMouseClickTool,
        CuaScreenshotTool,
    )

    manager = FunctionToolManager()

    assert manager.get_builtin_tool(CuaScreenshotTool).name == "astrbot_cua_screenshot"
    assert manager.get_builtin_tool(CuaMouseClickTool).name == "astrbot_cua_mouse_click"
    assert (
        manager.get_builtin_tool(CuaKeyboardTypeTool).name
        == "astrbot_cua_keyboard_type"
    )


def test_cua_runtime_tools_are_available_to_handoffs():
    manager = FunctionToolManager()

    tools = FunctionToolExecutor._get_runtime_computer_tools("sandbox", manager, "cua")

    assert "astrbot_cua_screenshot" in tools
    assert "astrbot_cua_mouse_click" in tools
    assert "astrbot_cua_keyboard_type" in tools
    assert "astrbot_cua_key_press" not in tools


def test_runtime_tool_selection_treats_none_booter_as_empty():
    manager = FunctionToolManager()

    tools = FunctionToolExecutor._get_runtime_computer_tools("sandbox", manager, None)

    assert "astrbot_execute_shell" in tools
    assert "astrbot_cua_screenshot" not in tools


def test_runtime_tool_selection_normalizes_cua_booter_case():
    manager = FunctionToolManager()

    tools = FunctionToolExecutor._get_runtime_computer_tools("sandbox", manager, "CUA")

    assert "astrbot_cua_screenshot" in tools


def test_cua_is_exposed_in_sandbox_config_metadata():
    items = _agent_computer_use_items()
    booter = items["provider_settings.sandbox.booter"]

    assert "cua" in booter["options"]
    assert "CUA" in booter["labels"]
    assert "provider_settings.sandbox.cua_image" in items
    assert "provider_settings.sandbox.cua_os_type" in items
    assert "provider_settings.sandbox.cua_ttl" in items
    assert "provider_settings.sandbox.cua_telemetry_enabled" in items
    assert "provider_settings.sandbox.cua_local" in items
    assert "provider_settings.sandbox.cua_api_key" in items
    assert (
        items["provider_settings.sandbox.cua_api_key"]["condition"][
            "provider_settings.sandbox.cua_local"
        ]
        is False
    )


_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


@pytest.mark.asyncio
async def test_screenshot_tool_returns_image_and_sends_file(monkeypatch, tmp_path):
    from astrbot.core.tools.computer_tools import cua as cua_tools
    from astrbot.core.tools.computer_tools.cua import CuaScreenshotTool

    sent_messages = []

    class FakeEvent:
        unified_msg_origin = "umo"
        role = "admin"

        async def send(self, message):
            sent_messages.append(message)

    class FakeAstrContext:
        event = FakeEvent()
        context = FakeContext(
            {
                "provider_settings": {
                    "computer_use_runtime": "sandbox",
                    "computer_use_require_admin": True,
                    "sandbox": {"booter": "cua"},
                }
            }
        )

    class FakeWrapper:
        context = FakeAstrContext()

    class FakeGUI:
        async def screenshot(self, path: str):
            Path(path).write_bytes(b"fake-png")
            return {
                "success": True,
                "path": path,
                "mime_type": "image/png",
                "base64": base64.b64encode(b"fake-png").decode(),
            }

    class FakeBooter:
        gui = FakeGUI()

    async def fake_get_booter(context, session_id):
        return FakeBooter()

    monkeypatch.setattr(cua_tools, "get_booter", fake_get_booter)
    monkeypatch.setattr(cua_tools, "get_astrbot_temp_path", lambda: str(tmp_path))

    result = await CuaScreenshotTool().call(FakeWrapper(), send_to_user=True)

    assert isinstance(result, mcp.types.CallToolResult)
    image_parts = [part for part in result.content if part.type == "image"]
    text_parts = [part for part in result.content if part.type == "text"]
    payload = json.loads(text_parts[0].text)
    assert image_parts[0].data == base64.b64encode(b"fake-png").decode()
    assert "base64" not in payload
    assert Path(payload["path"]).exists()
    assert sent_messages


@pytest.mark.parametrize(
    "screenshot_shape",
    [
        "data_url",
        "path_string",
        "save_object",
        "base64_dict",
    ],
)
@pytest.mark.asyncio
async def test_screenshot_tool_normalizes_supported_screenshot_shapes(
    monkeypatch,
    tmp_path,
    screenshot_shape,
):
    from astrbot.core.computer.booters.cua import CuaGUIComponent
    from astrbot.core.tools.computer_tools import cua as cua_tools
    from astrbot.core.tools.computer_tools.cua import CuaScreenshotTool

    sent_messages = []

    class FakeEvent:
        unified_msg_origin = "umo"
        role = "admin"

        async def send(self, message):
            sent_messages.append(message)

    class FakeAstrContext:
        event = FakeEvent()
        context = FakeContext(
            {
                "provider_settings": {
                    "computer_use_runtime": "sandbox",
                    "computer_use_require_admin": True,
                    "sandbox": {"booter": "cua"},
                }
            }
        )

    class FakeWrapper:
        context = FakeAstrContext()

    class SaveObject:
        def save(self, output, format):
            assert format == "PNG"
            output.write(_PNG_BYTES)

    class FakeSandbox:
        async def screenshot(self):
            if screenshot_shape == "data_url":
                encoded = base64.b64encode(_PNG_BYTES).decode()
                return f"data:image/png;base64,{encoded}"
            if screenshot_shape == "path_string":
                source_path = tmp_path / "source.png"
                source_path.write_bytes(_PNG_BYTES)
                return str(source_path)
            if screenshot_shape == "save_object":
                return SaveObject()
            return {"base64": base64.b64encode(_PNG_BYTES).decode()}

    class FakeBooter:
        gui = CuaGUIComponent(FakeSandbox())

    async def fake_get_booter(context, session_id):
        return FakeBooter()

    monkeypatch.setattr(cua_tools, "get_booter", fake_get_booter)
    monkeypatch.setattr(cua_tools, "get_astrbot_temp_path", lambda: str(tmp_path))

    result = await CuaScreenshotTool().call(FakeWrapper(), send_to_user=True)

    assert isinstance(result, mcp.types.CallToolResult)
    image_parts = [part for part in result.content if part.type == "image"]
    text_parts = [part for part in result.content if part.type == "text"]
    payload = json.loads(text_parts[0].text)
    assert "base64" not in payload
    assert payload["mime_type"] == "image/png"
    assert Path(payload["path"]).read_bytes() == _PNG_BYTES
    assert base64.b64decode(image_parts[0].data) == _PNG_BYTES
    assert sent_messages


@pytest.mark.asyncio
async def test_screenshot_tool_can_opt_in_to_llm_image_content(monkeypatch, tmp_path):
    from astrbot.core.tools.computer_tools import cua as cua_tools
    from astrbot.core.tools.computer_tools.cua import CuaScreenshotTool

    class FakeEvent:
        unified_msg_origin = "umo"
        role = "admin"

        async def send(self, message):
            pass

    class FakeAstrContext:
        event = FakeEvent()
        context = FakeContext(
            {"provider_settings": {"computer_use_require_admin": True}}
        )

    class FakeWrapper:
        context = FakeAstrContext()

    class FakeGUI:
        async def screenshot(self, path: str):
            Path(path).write_bytes(b"fake-png")
            return {
                "success": True,
                "path": path,
                "mime_type": "image/png",
                "base64": base64.b64encode(b"fake-png").decode(),
            }

    class FakeBooter:
        gui = FakeGUI()

    async def fake_get_booter(context, session_id):
        return FakeBooter()

    monkeypatch.setattr(cua_tools, "get_booter", fake_get_booter)
    monkeypatch.setattr(cua_tools, "get_astrbot_temp_path", lambda: str(tmp_path))

    result = await CuaScreenshotTool().call(
        FakeWrapper(), send_to_user=False, return_image_to_llm=True
    )

    image_parts = [part for part in result.content if part.type == "image"]
    text_parts = [part for part in result.content if part.type == "text"]
    payload = json.loads(text_parts[0].text)
    assert image_parts[0].data == base64.b64encode(b"fake-png").decode()
    assert "base64" not in payload


@pytest.mark.asyncio
async def test_screenshot_tool_can_opt_out_of_llm_image_content(monkeypatch, tmp_path):
    from astrbot.core.tools.computer_tools import cua as cua_tools
    from astrbot.core.tools.computer_tools.cua import CuaScreenshotTool

    class FakeEvent:
        unified_msg_origin = "umo"
        role = "admin"

        async def send(self, message):
            pass

    class FakeAstrContext:
        event = FakeEvent()
        context = FakeContext(
            {"provider_settings": {"computer_use_require_admin": True}}
        )

    class FakeWrapper:
        context = FakeAstrContext()

    class FakeGUI:
        async def screenshot(self, path: str):
            Path(path).write_bytes(b"fake-png")
            return {
                "success": True,
                "path": path,
                "mime_type": "image/png",
                "base64": base64.b64encode(b"fake-png").decode(),
            }

    class FakeBooter:
        gui = FakeGUI()

    async def fake_get_booter(context, session_id):
        return FakeBooter()

    monkeypatch.setattr(cua_tools, "get_booter", fake_get_booter)
    monkeypatch.setattr(cua_tools, "get_astrbot_temp_path", lambda: str(tmp_path))

    result = await CuaScreenshotTool().call(
        FakeWrapper(), send_to_user=False, return_image_to_llm=False
    )

    image_parts = [part for part in result.content if part.type == "image"]
    text_parts = [part for part in result.content if part.type == "text"]
    payload = json.loads(text_parts[0].text)
    assert image_parts == []
    assert "base64" not in payload


@pytest.mark.asyncio
async def test_cua_tools_return_permission_error_without_gui_lookup(monkeypatch):
    from astrbot.core.tools.computer_tools import cua as cua_tools
    from astrbot.core.tools.computer_tools.cua import (
        CuaKeyboardTypeTool,
        CuaMouseClickTool,
        CuaScreenshotTool,
    )

    sent_messages = []

    class FakeEvent:
        unified_msg_origin = "umo"
        role = "member"

        async def send(self, message):
            sent_messages.append(message)

    class FakeAstrContext:
        event = FakeEvent()
        context = FakeContext({"provider_settings": {}})

    class FakeWrapper:
        context = FakeAstrContext()

    async def fail_gui_lookup(context):
        raise AssertionError("GUI lookup should not run after permission failure")

    monkeypatch.setattr(cua_tools, "check_admin_permission", lambda *args: "denied")
    monkeypatch.setattr(cua_tools, "_get_gui_component", fail_gui_lookup)

    assert await CuaScreenshotTool().call(FakeWrapper()) == "denied"
    assert await CuaMouseClickTool().call(FakeWrapper(), x=1, y=2) == "denied"
    assert await CuaKeyboardTypeTool().call(FakeWrapper(), text="hello") == "denied"
    assert sent_messages == []


@pytest.mark.asyncio
async def test_cua_tools_include_exception_type_for_blank_error(monkeypatch):
    from astrbot.core.tools.computer_tools import cua as cua_tools
    from astrbot.core.tools.computer_tools.cua import CuaMouseClickTool

    class BlankError(Exception):
        def __str__(self):
            return ""

    class FakeEvent:
        unified_msg_origin = "umo"
        role = "admin"

    class FakeAstrContext:
        event = FakeEvent()
        context = FakeContext(
            {"provider_settings": {"computer_use_require_admin": True}}
        )

    class FakeWrapper:
        context = FakeAstrContext()

    async def fail_gui_lookup(context):
        raise BlankError()

    monkeypatch.setattr(cua_tools, "_get_gui_component", fail_gui_lookup)

    assert await CuaMouseClickTool().call(FakeWrapper(), x=1, y=2) == (
        "Error clicking CUA desktop: BlankError"
    )


@pytest.mark.asyncio
async def test_cua_mouse_click_tool_happy_path_forwards_args_and_serializes_json(
    monkeypatch,
):
    from astrbot.core.tools.computer_tools import cua as cua_tools
    from astrbot.core.tools.computer_tools.cua import CuaMouseClickTool

    class FakeEvent:
        unified_msg_origin = "umo"
        role = "admin"

    class FakeAstrContext:
        event = FakeEvent()
        context = FakeContext(
            {"provider_settings": {"computer_use_require_admin": True}}
        )

    class FakeWrapper:
        context = FakeAstrContext()

    class FakeGui:
        def __init__(self):
            self.clicked_args = None

        async def click(self, x: int, y: int, button: str = "left"):
            self.clicked_args = (x, y, button)
            return {"status": "ok", "x": x, "y": y, "button": button}

    fake_gui = FakeGui()
    get_gui_called = {"value": False}
    wrapper = FakeWrapper()

    async def fake_get_gui_component(context):
        get_gui_called["value"] = True
        assert context is wrapper
        return fake_gui

    monkeypatch.setattr(cua_tools, "_get_gui_component", fake_get_gui_component)

    result = await CuaMouseClickTool().call(wrapper, x=10, y=20, button="right")

    assert get_gui_called["value"] is True
    assert fake_gui.clicked_args == (10, 20, "right")
    assert json.loads(result) == {
        "status": "ok",
        "x": 10,
        "y": 20,
        "button": "right",
    }


@pytest.mark.asyncio
async def test_cua_keyboard_type_tool_happy_path_forwards_args_and_serializes_json(
    monkeypatch,
):
    from astrbot.core.tools.computer_tools import cua as cua_tools
    from astrbot.core.tools.computer_tools.cua import CuaKeyboardTypeTool

    class FakeEvent:
        unified_msg_origin = "umo"
        role = "admin"

    class FakeAstrContext:
        event = FakeEvent()
        context = FakeContext(
            {"provider_settings": {"computer_use_require_admin": True}}
        )

    class FakeWrapper:
        context = FakeAstrContext()

    class FakeGui:
        def __init__(self):
            self.typed_text_args = None

        async def type_text(self, text: str):
            self.typed_text_args = (text,)
            return {"status": "ok", "text": text}

    fake_gui = FakeGui()
    get_gui_called = {"value": False}
    wrapper = FakeWrapper()

    async def fake_get_gui_component(context):
        get_gui_called["value"] = True
        assert context is wrapper
        return fake_gui

    monkeypatch.setattr(cua_tools, "_get_gui_component", fake_get_gui_component)

    result = await CuaKeyboardTypeTool().call(wrapper, text="Hello CUA")

    assert get_gui_called["value"] is True
    assert fake_gui.typed_text_args == ("Hello CUA",)
    assert json.loads(result) == {"status": "ok", "text": "Hello CUA"}
