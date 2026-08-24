from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
import sys

import pytest

from astrbot.core.computer.booters import local as local_booter
from astrbot.core.computer.booters.local import LocalShellComponent


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
    monkeypatch.setattr(local_booter.shutil, "which", lambda _cmd: None)

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


def test_local_shell_component_prefers_pwsh_when_available(monkeypatch):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return _FakePopen(stdout=b"")

    monkeypatch.setattr(subprocess, "Popen", fake_run)
    monkeypatch.setattr(local_booter.sys, "platform", "win32")
    monkeypatch.setattr(
        local_booter.shutil,
        "which",
        lambda cmd: "/opt/pwsh" if cmd == "pwsh" else None,
    )

    result = asyncio.run(LocalShellComponent().exec("Get-ChildItem"))

    assert result["exit_code"] == 0
    assert calls[0][0][0] == [
        "pwsh.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "Get-ChildItem",
    ]
    assert calls[0][1]["shell"] is False


def test_exec_falls_back_to_powershell_when_pwsh_missing(monkeypatch):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return _FakePopen(stdout=b"")

    monkeypatch.setattr(subprocess, "Popen", fake_run)
    monkeypatch.setattr(local_booter.sys, "platform", "win32")
    monkeypatch.setattr(local_booter.shutil, "which", lambda _cmd: None)

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
    monkeypatch.setattr(local_booter.shutil, "which", lambda _cmd: None)
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


@pytest.mark.asyncio
async def test_managed_shell_prefers_pwsh_when_available(monkeypatch, tmp_path):
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
        local_booter.shutil,
        "which",
        lambda cmd: "/opt/pwsh" if cmd == "pwsh" else None,
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
        "pwsh.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "Get-ChildItem",
    )
    assert "creationflags" in calls[0][1]


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
    monkeypatch.setattr(local_booter.shutil, "which", lambda _cmd: None)

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
    assert result["stdout"].splitlines() == ["hello"]
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
        assert result["stdout"].splitlines() == ["ready"]
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
        assert output.splitlines() == ["got:hello"]
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

        assert output.splitlines() == ["x" * 25000]
        assert result["session_closed"] is True
        assert await shell.list_sessions(
            owner_id="owner-a",
            requester_id="user-a",
            requester_is_admin=False,
        ) == {"sessions": []}
    finally:
        await shell.shutdown_sessions()
