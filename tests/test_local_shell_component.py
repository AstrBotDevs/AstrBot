from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from astrbot.core.computer.booters import local as local_booter
from astrbot.core.computer.booters.local import (
    LocalFileSystemComponent,
    LocalPythonComponent,
    LocalShellComponent,
)


class _FakePopen:
    def __init__(self, stdout: bytes, stderr: bytes = b"", returncode: int = 0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self.pid = 12345

    def communicate(self, timeout=None):
        return self._stdout, self._stderr

    def wait(self, timeout=None):
        pass


class _FakeTaskkillResult:
    def __init__(self, returncode: int):
        self.returncode = returncode


def _python_command(code: str) -> str:
    """Build a shell-safe Python command for the current operating system."""
    args = [sys.executable, "-u", "-c", code]
    return subprocess.list2cmdline(args) if os.name == "nt" else shlex.join(args)


def test_local_shell_component_decodes_utf8_output(monkeypatch):
    def fake_run(*args, **kwargs):
        _ = args, kwargs
        return _FakePopen(stdout="技能内容".encode())

    monkeypatch.setattr(subprocess, "Popen", fake_run)

    result = asyncio.run(LocalShellComponent().exec("dummy"))

    assert result["stdout"] == "技能内容"
    assert result["stderr"] == ""
    assert result["exit_code"] == 0


def test_local_shell_component_uses_windows_powershell(monkeypatch):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return _FakePopen(stdout=b"")

    monkeypatch.setattr(subprocess, "Popen", fake_run)
    monkeypatch.setattr(local_booter.sys, "platform", "win32")

    result = asyncio.run(LocalShellComponent().exec("Get-ChildItem"))

    assert result["exit_code"] == 0
    assert calls[0][0][0] == [
        "powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "Get-ChildItem",
    ]
    assert calls[0][1]["shell"] is False


def test_local_shell_component_keeps_platform_shell_outside_windows(monkeypatch):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return _FakePopen(stdout=b"")

    monkeypatch.setattr(subprocess, "Popen", fake_run)
    monkeypatch.setattr(local_booter.sys, "platform", "linux")

    result = asyncio.run(LocalShellComponent().exec("pwd"))

    assert result["exit_code"] == 0
    assert calls[0][0][0] == "pwd"
    assert calls[0][1]["shell"] is True


@pytest.mark.asyncio
async def test_managed_shell_uses_windows_powershell(monkeypatch, tmp_path):
    calls = []

    class FakeStdout:
        def __init__(self):
            self.chunks = [b"done\n", b""]

        async def read(self, _limit):
            return self.chunks.pop(0)

    class FakeProcess:
        def __init__(self):
            self.pid = 12345
            self.returncode = None
            self.stdout = FakeStdout()
            self.stdin = None

        async def wait(self):
            self.returncode = 0
            return 0

    async def fake_create_subprocess_exec(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess()

    async def fail_create_subprocess_shell(*_args, **_kwargs):
        raise AssertionError("Windows managed commands must not use cmd.exe.")

    monkeypatch.setattr(local_booter.sys, "platform", "win32")
    monkeypatch.setattr(
        local_booter.asyncio,
        "create_subprocess_exec",
        fake_create_subprocess_exec,
    )
    monkeypatch.setattr(
        local_booter.asyncio,
        "create_subprocess_shell",
        fail_create_subprocess_shell,
    )

    result = await LocalShellComponent().exec_managed(
        "Get-ChildItem",
        owner_id="owner-a",
        creator_id="user-a",
        creator_is_admin=False,
        sandboxed=False,
        cwd=str(tmp_path),
        yield_time_ms=5_000,
    )

    assert result["status"] == "completed"
    assert result["stdout"] == "done\n"
    assert calls[0][0] == (
        "powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "Get-ChildItem",
    )
    assert "creationflags" in calls[0][1]


def test_linux_bwrap_command_is_workspace_only_and_clears_environment(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(local_booter.sys, "platform", "linux")
    monkeypatch.setattr(local_booter.shutil, "which", lambda name: f"/usr/bin/{name}")

    command = local_booter._build_local_sandbox_command(
        ["/bin/sh", "-c", "pwd"],
        workspace=tmp_path,
        env={"CUSTOM_VALUE": "visible"},
    )

    workspace = str(tmp_path.resolve())
    assert command[0] == "/usr/bin/bwrap"
    assert "--unshare-all" in command
    assert "--new-session" in command
    assert "--clearenv" in command
    assert "--share-net" not in command
    assert command[command.index("--size") + 1] == str(256 * 1024 * 1024)
    assert ["--bind", workspace, workspace] == command[
        command.index("--bind") : command.index("--bind") + 3
    ]
    assert ["--setenv", "CUSTOM_VALUE", "visible"] == command[
        command.index("CUSTOM_VALUE") - 1 : command.index("CUSTOM_VALUE") + 2
    ]
    assert command[-3:] == ["/bin/sh", "-c", "pwd"]
    bind_sources = [
        command[index + 1]
        for index, value in enumerate(command)
        if value in {"--bind", "--ro-bind"}
    ]
    assert str(Path.home()) not in bind_sources

    read_only_command = local_booter._build_local_sandbox_command(
        ["/usr/bin/rg", "needle", "."],
        workspace=tmp_path,
        workspace_writable=False,
    )
    assert ["--ro-bind", workspace, workspace] == read_only_command[
        read_only_command.index(workspace) - 1 : read_only_command.index(workspace) + 2
    ]


def test_linux_bwrap_command_fails_closed_when_bwrap_is_missing(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(local_booter.sys, "platform", "linux")
    monkeypatch.setattr(local_booter.shutil, "which", lambda _name: None)

    with pytest.raises(RuntimeError, match="bubblewrap"):
        local_booter._build_local_sandbox_command(
            ["/bin/sh", "-c", "pwd"],
            workspace=tmp_path,
        )


def test_macos_seatbelt_command_restricts_profile_and_environment(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(local_booter.sys, "platform", "darwin")
    monkeypatch.setattr(
        local_booter.shutil,
        "which",
        lambda name, **_kwargs: f"/usr/bin/{name}",
    )

    command = local_booter._build_local_sandbox_command(
        ["/bin/sh", "-c", "pwd"],
        workspace=tmp_path,
        env={"CUSTOM_VALUE": "visible", "PATH": "untrusted"},
    )

    profile = command[command.index("-p") + 1]
    environment_start = command.index("-i") + 1
    launcher_start = command.index(
        str(Path(sys.executable).resolve()),
        environment_start,
    )
    environment = command[environment_start:launcher_start]
    workspace = str(tmp_path.resolve())

    assert command[0] == "/usr/bin/sandbox-exec"
    assert f"WORKSPACE={workspace}" in command
    assert '(import "system.sb")' in profile
    assert "(deny default)" in profile
    assert "(deny network*)" in profile
    assert '(literal "/usr/bin/open")' in profile
    assert "(deny appleevent-send)" in profile
    assert '(global-name "com.apple.coreservices.launchservicesd")' in profile
    assert "(allow file-write*" in profile
    assert command[command.index("-p") + 2 : command.index("-p") + 4] == [
        "/usr/bin/env",
        "-i",
    ]
    assert "CUSTOM_VALUE=visible" in environment
    assert environment[-4:] == [
        f"PATH={Path(sys.executable).resolve().parent}:/usr/bin:/bin",
        f"HOME={workspace}",
        f"TMPDIR={workspace}",
        "LANG=C.UTF-8",
    ]
    assert command[-3:] == ["/bin/sh", "-c", "pwd"]

    read_only_command = local_booter._build_local_sandbox_command(
        ["/usr/bin/rg", "needle", "."],
        workspace=tmp_path,
        workspace_writable=False,
    )
    read_only_profile = read_only_command[read_only_command.index("-p") + 1]
    assert "(deny file-write*)" in read_only_profile
    assert "(allow file-write*" not in read_only_profile


def test_macos_seatbelt_command_fails_closed_when_tool_is_missing(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(local_booter.sys, "platform", "darwin")
    monkeypatch.setattr(
        local_booter.shutil,
        "which",
        lambda _name, **_kwargs: None,
    )

    with pytest.raises(RuntimeError, match="Seatbelt"):
        local_booter._build_local_sandbox_command(
            ["/bin/sh", "-c", "pwd"],
            workspace=tmp_path,
        )


@pytest.mark.skipif(sys.platform != "darwin", reason="Seatbelt is macOS-only")
def test_macos_seatbelt_enforces_workspace_network_and_environment(tmp_path):
    outside_file = tmp_path.parent / "seatbelt-outside.txt"
    outside_file.write_text("host secret", encoding="utf-8")
    (tmp_path / "input.txt").write_text("allowed", encoding="utf-8")
    code = f"""
import os
import pathlib
import socket
import subprocess

workspace = pathlib.Path.cwd()
assert (workspace / "input.txt").read_text() == "allowed"
(workspace / "output.txt").write_text("written")
try:
    pathlib.Path({str(outside_file)!r}).read_text()
except OSError:
    pass
else:
    raise SystemExit("host read unexpectedly allowed")
try:
    os.kill(int(os.environ["HOST_PID"]), 0)
except OSError:
    pass
else:
    raise SystemExit("host process unexpectedly visible")
try:
    opened = subprocess.run(
        ["/usr/bin/open", "https://example.com"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0
except OSError:
    opened = False
if opened:
    raise SystemExit("URL broker unexpectedly available")
try:
    sock = socket.socket()
    sock.settimeout(1)
    connected = sock.connect_ex(("1.1.1.1", 53)) == 0
except OSError:
    connected = False
if connected:
    raise SystemExit("network unexpectedly available")
assert os.environ.get("HOST_SECRET") is None
"""
    command = local_booter._build_local_sandbox_command(
        [sys.executable, "-c", code],
        workspace=tmp_path,
        env={"HOST_PID": str(os.getpid())},
    )

    result = subprocess.run(
        command,
        cwd=tmp_path,
        env={"PATH": os.defpath, "HOST_SECRET": "must-not-leak"},
        capture_output=True,
        timeout=10,
    )

    assert result.returncode == 0, local_booter._decode_shell_output(result.stderr)
    assert (tmp_path / "output.txt").read_text(encoding="utf-8") == "written"


@pytest.mark.skipif(sys.platform != "darwin", reason="Seatbelt is macOS-only")
def test_macos_read_only_seatbelt_grep_cannot_follow_outside_ancestor_symlink(
    tmp_path,
):
    rg_path = shutil.which("rg")
    if not rg_path:
        pytest.skip("ripgrep is unavailable")

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    inside_file = workspace / "inside.txt"
    inside_file.write_text("visible-needle\n", encoding="utf-8")
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_file = outside_dir / "secret.txt"
    outside_file.write_text("host-secret-needle\n", encoding="utf-8")
    (workspace / "redirect").symlink_to(outside_dir, target_is_directory=True)

    positive_command = local_booter._build_local_sandbox_command(
        [str(Path(rg_path).resolve()), "visible-needle", "--", str(inside_file)],
        workspace=workspace,
        workspace_writable=False,
    )
    positive = subprocess.run(
        positive_command,
        cwd=workspace,
        env={"PATH": os.defpath},
        capture_output=True,
        timeout=10,
    )
    assert positive.returncode == 0
    assert b"visible-needle" in positive.stdout

    escaped_path = workspace / "redirect" / "secret.txt"
    escaped_command = local_booter._build_local_sandbox_command(
        [str(Path(rg_path).resolve()), "host-secret-needle", "--", str(escaped_path)],
        workspace=workspace,
        workspace_writable=False,
    )
    escaped = subprocess.run(
        escaped_command,
        cwd=workspace,
        env={"PATH": os.defpath},
        capture_output=True,
        timeout=10,
    )
    assert b"host-secret-needle" not in escaped.stdout


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="bubblewrap is Linux-only",
)
def test_linux_read_only_bwrap_grep_cannot_follow_outside_ancestor_symlink(
    tmp_path,
):
    if not shutil.which("bwrap"):
        pytest.skip("bubblewrap is unavailable")
    if sys.version_info >= (3, 14) and not shutil.which("rg"):
        pytest.skip("ripgrep is unavailable")

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    inside_file = workspace / "inside.txt"
    inside_file.write_text("visible-needle\n", encoding="utf-8")
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_file = outside_dir / "secret.txt"
    outside_file.write_text("host-secret-needle\n", encoding="utf-8")
    (workspace / "redirect").symlink_to(outside_dir, target_is_directory=True)

    positive = asyncio.run(
        LocalFileSystemComponent().search_files(
            "visible-needle",
            path=str(inside_file),
            sandboxed=True,
            sandbox_root=str(workspace),
        )
    )
    assert positive["success"] is True
    assert "visible-needle" in positive["content"]

    escaped_path = workspace / "redirect" / "secret.txt"
    escaped = asyncio.run(
        LocalFileSystemComponent().search_files(
            "host-secret-needle",
            path=str(escaped_path),
            sandboxed=True,
            sandbox_root=str(workspace),
        )
    )
    assert "host-secret-needle" not in escaped.get("content", "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("platform_name", "sandbox_executable"),
    [
        ("linux", "/usr/bin/bwrap"),
        ("darwin", "/usr/bin/sandbox-exec"),
    ],
)
async def test_managed_shell_uses_platform_sandbox(
    monkeypatch,
    tmp_path,
    platform_name,
    sandbox_executable,
):
    calls = []

    class FakeStdout:
        def __init__(self):
            self.chunks = [b"done\n", b""]

        async def read(self, _limit):
            return self.chunks.pop(0)

    class FakeProcess:
        def __init__(self):
            self.pid = 12345
            self.returncode = None
            self.stdout = FakeStdout()
            self.stdin = None

        async def wait(self):
            self.returncode = 0
            return 0

    async def fake_create_subprocess_exec(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess()

    async def fail_create_subprocess_shell(*_args, **_kwargs):
        raise AssertionError("Sandboxed commands must use an argument vector.")

    monkeypatch.setattr(local_booter.sys, "platform", platform_name)
    monkeypatch.setattr(
        local_booter.shutil,
        "which",
        lambda _name, **_kwargs: sandbox_executable,
    )
    monkeypatch.setattr(
        local_booter.asyncio,
        "create_subprocess_exec",
        fake_create_subprocess_exec,
    )
    monkeypatch.setattr(
        local_booter.asyncio,
        "create_subprocess_shell",
        fail_create_subprocess_shell,
    )

    result = await LocalShellComponent().exec_managed(
        "pwd",
        owner_id="owner-a",
        cwd=str(tmp_path),
        yield_time_ms=5_000,
        sandboxed=True,
    )

    assert result["status"] == "completed"
    assert result["stdout"] == "done\n"
    assert calls[0][0][0] == sandbox_executable
    assert calls[0][0][-3:] == ("/bin/sh", "-c", "pwd")
    assert calls[0][1]["env"] == {"PATH": os.defpath}
    assert calls[0][1]["start_new_session"] is True


@pytest.mark.asyncio
async def test_sandboxed_managed_shell_stops_at_output_limit(monkeypatch, tmp_path):
    process_stopped = asyncio.Event()

    class FakeStdout:
        def __init__(self):
            self.chunks = [b"123456", b""]

        async def read(self, _limit):
            return self.chunks.pop(0)

    class FakeProcess:
        def __init__(self):
            self.pid = 12345
            self.returncode = None
            self.stdout = FakeStdout()
            self.stdin = None

        async def wait(self):
            await process_stopped.wait()
            self.returncode = -15
            return self.returncode

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return FakeProcess()

    def fake_killpg(pid, sig):
        assert pid == 12345
        assert sig == local_booter.signal.SIGTERM
        process_stopped.set()

    monkeypatch.setattr(local_booter.sys, "platform", "linux")
    monkeypatch.setattr(local_booter.shutil, "which", lambda _name: "/usr/bin/bwrap")
    monkeypatch.setattr(local_booter, "_LOCAL_SANDBOX_MAX_OUTPUT_BYTES", 5)
    monkeypatch.setattr(
        local_booter.asyncio,
        "create_subprocess_exec",
        fake_create_subprocess_exec,
    )
    monkeypatch.setattr(local_booter.os, "killpg", fake_killpg)

    result = await LocalShellComponent().exec_managed(
        "yes",
        owner_id="owner-a",
        cwd=str(tmp_path),
        yield_time_ms=5_000,
        sandboxed=True,
    )

    assert result["status"] == "output_limited"
    assert result["stdout"] == "12345"
    assert result["session_closed"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("platform_name", "sandbox_executable"),
    [
        ("linux", "/usr/bin/bwrap"),
        ("darwin", "/usr/bin/sandbox-exec"),
    ],
)
async def test_local_python_uses_platform_sandbox(
    monkeypatch,
    tmp_path,
    platform_name,
    sandbox_executable,
):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        kwargs["stdout"].write(b"done\n")
        return subprocess.CompletedProcess(args[0], 0)

    monkeypatch.setattr(local_booter.sys, "platform", platform_name)
    monkeypatch.setattr(
        local_booter.shutil,
        "which",
        lambda _name, **_kwargs: sandbox_executable,
    )
    monkeypatch.setattr(local_booter.subprocess, "run", fake_run)

    result = await LocalPythonComponent().exec(
        "print('done')",
        cwd=str(tmp_path),
        sandboxed=True,
    )

    assert result["data"]["output"]["text"] == "done\n"
    assert calls[0][0][0][0] == sandbox_executable
    assert calls[0][0][0][-3:] == [
        str(Path(sys.executable).resolve()),
        "-c",
        "print('done')",
    ]
    assert calls[0][1]["env"] == {"PATH": os.defpath}
    assert "capture_output" not in calls[0][1]


@pytest.mark.asyncio
async def test_sandboxed_local_python_caps_returned_output(monkeypatch, tmp_path):
    def fake_run(*args, **kwargs):
        kwargs["stdout"].write(b"123456")
        return subprocess.CompletedProcess(args[0], 0)

    monkeypatch.setattr(local_booter.sys, "platform", "linux")
    monkeypatch.setattr(local_booter.shutil, "which", lambda _name: "/usr/bin/bwrap")
    monkeypatch.setattr(local_booter, "_LOCAL_SANDBOX_MAX_OUTPUT_BYTES", 5)
    monkeypatch.setattr(local_booter.subprocess, "run", fake_run)

    result = await LocalPythonComponent().exec(
        "print('large output')",
        cwd=str(tmp_path),
        sandboxed=True,
    )

    assert result["data"]["output"]["text"] == "12345"
    assert result["data"]["error"] == "Execution output exceeded 5 bytes."


def test_local_shell_component_prefers_utf8_before_windows_locale(
    monkeypatch,
):
    def fake_run(*args, **kwargs):
        _ = args, kwargs
        return _FakePopen(stdout="技能内容".encode())

    monkeypatch.setattr(subprocess, "Popen", fake_run)
    monkeypatch.setattr(local_booter.os, "name", "nt", raising=False)
    monkeypatch.setattr(
        local_booter.locale,
        "getpreferredencoding",
        lambda _do_setlocale=False: "cp936",
    )

    result = asyncio.run(LocalShellComponent().exec("dummy"))

    assert result["stdout"] == "技能内容"
    assert result["stderr"] == ""
    assert result["exit_code"] == 0


def test_local_shell_component_falls_back_to_gbk_on_windows(monkeypatch):
    def fake_run(*args, **kwargs):
        _ = args, kwargs
        return _FakePopen(stdout="微博热搜".encode("gbk"))

    monkeypatch.setattr(subprocess, "Popen", fake_run)
    monkeypatch.setattr(local_booter.os, "name", "nt", raising=False)
    monkeypatch.setattr(
        local_booter.locale,
        "getpreferredencoding",
        lambda _do_setlocale=False: "cp1252",
    )

    result = asyncio.run(LocalShellComponent().exec("dummy"))

    assert result["stdout"] == "微博热搜"
    assert result["stderr"] == ""
    assert result["exit_code"] == 0


def test_local_shell_component_falls_back_to_utf8_replace(monkeypatch):
    def fake_run(*args, **kwargs):
        _ = args, kwargs
        return _FakePopen(stdout=b"\xffabc")

    monkeypatch.setattr(subprocess, "Popen", fake_run)
    monkeypatch.setattr(local_booter.os, "name", "posix", raising=False)
    monkeypatch.setattr(
        local_booter.locale,
        "getpreferredencoding",
        lambda _do_setlocale=False: "utf-8",
    )

    result = asyncio.run(LocalShellComponent().exec("dummy"))

    assert result["stdout"] == "\ufffdabc"


def test_local_shell_component_falls_back_when_windows_taskkill_fails(monkeypatch):
    class TimeoutPopen:
        pid = 12345

        def __init__(self):
            self.killed = False
            self.wait_timeout = None

        def communicate(self, timeout=None):
            raise subprocess.TimeoutExpired(cmd="dummy", timeout=timeout)

        def kill(self):
            self.killed = True

        def wait(self, timeout=None):
            self.wait_timeout = timeout

    proc = TimeoutPopen()

    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: proc)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: _FakeTaskkillResult(returncode=1),
    )
    monkeypatch.setattr(local_booter.sys, "platform", "win32")

    with pytest.raises(subprocess.TimeoutExpired):
        asyncio.run(LocalShellComponent().exec("dummy", timeout=1))

    assert proc.killed
    assert proc.wait_timeout == 5


@pytest.mark.asyncio
async def test_managed_shell_returns_completed_output_without_open_session():
    shell = LocalShellComponent()

    result = await shell.exec_managed(
        _python_command("print('hello')"),
        owner_id="owner-a",
        creator_id="user-a",
        creator_is_admin=False,
        sandboxed=False,
        yield_time_ms=5_000,
    )

    assert result["status"] == "completed"
    assert result["stdout"] == "hello\n"
    assert result["exit_code"] == 0
    assert result["session_closed"] is True
    assert await shell.list_sessions(
        owner_id="owner-a",
        requester_id="user-a",
        requester_is_admin=False,
    ) == {"sessions": []}


@pytest.mark.asyncio
async def test_managed_shell_allows_creator_and_conversation_admin():
    shell = LocalShellComponent()
    result = await shell.exec_managed(
        _python_command("import time; print('ready', flush=True); time.sleep(30)"),
        owner_id="owner-a",
        creator_id="user-a",
        creator_is_admin=False,
        sandboxed=True,
        yield_time_ms=200,
    )

    try:
        assert result["status"] == "running"
        assert result["stdout"] == "ready\n"
        session_id = result["session_id"]
        assert (
            await shell.list_sessions(
                owner_id="owner-b",
                requester_id="user-a",
                requester_is_admin=False,
            )
        )["sessions"] == []
        sessions = (
            await shell.list_sessions(
                owner_id="owner-a",
                requester_id="user-a",
                requester_is_admin=False,
            )
        )["sessions"]
        assert [item["session_id"] for item in sessions] == [session_id]
        assert sessions[0]["sandboxed"] is True

        admin_sessions = (
            await shell.list_sessions(
                owner_id="owner-a",
                requester_id="admin-user",
                requester_is_admin=True,
            )
        )["sessions"]
        assert [item["session_id"] for item in admin_sessions] == [session_id]
        stopped = await shell.terminate_session(
            owner_id="owner-a",
            requester_id="admin-user",
            requester_is_admin=True,
            session_id=session_id,
        )

        assert stopped["status"] == "terminated"
        assert stopped["exit_code"] is not None
        assert stopped["session_closed"] is True
        assert await shell.list_sessions(
            owner_id="owner-a",
            requester_id="user-a",
            requester_is_admin=False,
        ) == {"sessions": []}
    finally:
        await shell.shutdown_sessions()


@pytest.mark.asyncio
async def test_managed_shell_rejects_cross_user_session_access():
    shell = LocalShellComponent()
    result = await shell.exec_managed(
        _python_command("import time; input(); time.sleep(30)"),
        owner_id="group-umo",
        creator_id="admin-user",
        creator_is_admin=True,
        sandboxed=False,
        yield_time_ms=100,
    )

    try:
        session_id = result["session_id"]
        member_access = {
            "owner_id": "group-umo",
            "requester_id": "member-user",
            "requester_is_admin": False,
        }
        demoted_creator_access = {
            "owner_id": "group-umo",
            "requester_id": "admin-user",
            "requester_is_admin": False,
        }
        other_conversation_admin_access = {
            "owner_id": "other-group-umo",
            "requester_id": "other-admin",
            "requester_is_admin": True,
        }

        assert await shell.list_sessions(**member_access) == {"sessions": []}
        assert await shell.list_sessions(**demoted_creator_access) == {"sessions": []}
        assert await shell.list_sessions(**other_conversation_admin_access) == {
            "sessions": []
        }
        with pytest.raises(ValueError, match="was not found"):
            await shell.poll_session(
                **member_access,
                session_id=session_id,
                cursor=0,
            )
        with pytest.raises(ValueError, match="was not found"):
            await shell.write_session(
                **member_access,
                session_id=session_id,
                chars="attacker-input\n",
            )
        with pytest.raises(ValueError, match="was not found"):
            await shell.interrupt_session(
                **member_access,
                session_id=session_id,
            )
        with pytest.raises(ValueError, match="was not found"):
            await shell.poll_session(
                **demoted_creator_access,
                session_id=session_id,
                cursor=0,
            )
        with pytest.raises(ValueError, match="was not found"):
            await shell.terminate_session(
                **other_conversation_admin_access,
                session_id=session_id,
            )
        with pytest.raises(ValueError, match="was not found"):
            await shell.terminate_session(
                **member_access,
                session_id=session_id,
            )

        assert shell._sessions[session_id].process.returncode is None
        admin_sessions = await shell.list_sessions(
            owner_id="group-umo",
            requester_id="admin-user",
            requester_is_admin=True,
        )
        assert [item["session_id"] for item in admin_sessions["sessions"]] == [
            session_id
        ]
        stopped = await shell.terminate_session(
            owner_id="group-umo",
            requester_id="admin-user",
            requester_is_admin=True,
            session_id=session_id,
        )
        assert stopped["status"] == "terminated"
    finally:
        await shell.shutdown_sessions()


@pytest.mark.asyncio
async def test_managed_shell_accepts_stdin_and_polls_incremental_output():
    shell = LocalShellComponent()
    result = await shell.exec_managed(
        _python_command("value = input(); print(f'got:{value}', flush=True)"),
        owner_id="owner-a",
        creator_id="user-a",
        creator_is_admin=False,
        sandboxed=True,
        yield_time_ms=100,
    )

    try:
        assert result["status"] == "running"
        await shell.write_session(
            owner_id="owner-a",
            requester_id="user-a",
            requester_is_admin=False,
            session_id=result["session_id"],
            chars="hello\n",
        )
        completed = await shell.poll_session(
            owner_id="owner-a",
            requester_id="user-a",
            requester_is_admin=False,
            session_id=result["session_id"],
            yield_time_ms=5_000,
        )
        output = completed["stdout"]
        if completed["status"] == "running":
            completed = await shell.poll_session(
                owner_id="owner-a",
                requester_id="user-a",
                requester_is_admin=False,
                session_id=result["session_id"],
                yield_time_ms=5_000,
            )
            output += completed["stdout"]

        assert completed["status"] == "completed"
        assert output == "got:hello\n"
        assert completed["session_closed"] is True
    finally:
        await shell.shutdown_sessions()


@pytest.mark.asyncio
async def test_managed_shell_hard_timeout_terminates_session():
    shell = LocalShellComponent()
    result = await shell.exec_managed(
        _python_command("import time; time.sleep(30)"),
        owner_id="owner-a",
        creator_id="user-a",
        creator_is_admin=False,
        sandboxed=False,
        timeout=1,
        yield_time_ms=0,
    )

    try:
        timed_out = await shell.poll_session(
            owner_id="owner-a",
            requester_id="user-a",
            requester_is_admin=False,
            session_id=result["session_id"],
            yield_time_ms=3_000,
        )

        assert timed_out["status"] == "timed_out"
        assert timed_out["exit_code"] is not None
        assert timed_out["session_closed"] is True
    finally:
        await shell.shutdown_sessions()


@pytest.mark.asyncio
async def test_managed_shell_keeps_completed_session_until_output_is_drained():
    shell = LocalShellComponent()
    result = await shell.exec_managed(
        _python_command("print('x' * 25000)"),
        owner_id="owner-a",
        creator_id="user-a",
        creator_is_admin=False,
        sandboxed=False,
        yield_time_ms=5_000,
        max_output_chars=10_000,
    )

    try:
        assert result["status"] == "completed"
        assert result["has_more"] is True
        output = result["stdout"]
        while result["has_more"]:
            result = await shell.poll_session(
                owner_id="owner-a",
                requester_id="user-a",
                requester_is_admin=False,
                session_id=result["session_id"],
                max_output_chars=10_000,
            )
            output += result["stdout"]

        assert output == f"{'x' * 25000}\n"
        assert result["session_closed"] is True
        assert await shell.list_sessions(
            owner_id="owner-a",
            requester_id="user-a",
            requester_is_admin=False,
        ) == {"sessions": []}
    finally:
        await shell.shutdown_sessions()
