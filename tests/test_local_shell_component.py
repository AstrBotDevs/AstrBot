import asyncio
import shlex
import signal
import subprocess
import sys

import pytest

from astrbot.core.computer.booters import local as local_booter
from astrbot.core.computer.booters.local import LocalShellComponent


def _python_command(code: str) -> str:
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"


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


def test_local_shell_component_decodes_utf8_output(monkeypatch):
    def fake_run(*args, **kwargs):
        _ = args, kwargs
        return _FakePopen(stdout="技能内容".encode())

    monkeypatch.setattr(subprocess, "Popen", fake_run)

    result = asyncio.run(LocalShellComponent().exec("dummy"))

    assert result["stdout"] == "技能内容"
    assert result["stderr"] == ""
    assert result["exit_code"] == 0


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
    monkeypatch.setattr(
        subprocess,
        "CREATE_NEW_PROCESS_GROUP",
        0x00000200,
        raising=False,
    )
    monkeypatch.setattr(local_booter.sys, "platform", "win32")

    with pytest.raises(subprocess.TimeoutExpired):
        asyncio.run(LocalShellComponent().exec("dummy", timeout=1))

    assert proc.killed
    assert proc.wait_timeout == 5


def test_local_shell_component_kills_posix_process_group_on_timeout(monkeypatch):
    """A shell timeout must reap commands spawned by the shell as well."""

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
    popen_kwargs = {}
    killed_groups = []
    expected_signal = getattr(signal, "SIGKILL", signal.SIGTERM)

    def fake_popen(*_args, **kwargs):
        popen_kwargs.update(kwargs)
        return proc

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(local_booter.sys, "platform", "linux")
    monkeypatch.setattr(
        local_booter.signal,
        "SIGKILL",
        expected_signal,
        raising=False,
    )
    monkeypatch.setattr(
        local_booter.os,
        "killpg",
        lambda pid, sig: killed_groups.append((pid, sig)),
        raising=False,
    )

    with pytest.raises(subprocess.TimeoutExpired):
        asyncio.run(LocalShellComponent().exec("dummy", timeout=1))

    assert popen_kwargs["start_new_session"] is True
    assert killed_groups == [(proc.pid, expected_signal)]
    assert proc.killed is False
    assert proc.wait_timeout == 5


def test_local_shell_component_starts_a_windows_process_group(monkeypatch):
    """Windows commands need a group so their complete tree is controllable."""
    popen_kwargs = {}

    def fake_popen(*_args, **kwargs):
        popen_kwargs.update(kwargs)
        return _FakePopen(stdout=b"")

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        subprocess,
        "CREATE_NEW_PROCESS_GROUP",
        0x00000200,
        raising=False,
    )
    monkeypatch.setattr(local_booter.sys, "platform", "win32")

    result = asyncio.run(LocalShellComponent().exec("dummy"))

    assert result["exit_code"] == 0
    assert popen_kwargs["creationflags"] == subprocess.CREATE_NEW_PROCESS_GROUP
    assert "start_new_session" not in popen_kwargs


def test_local_shell_component_prefers_powershell_on_windows(monkeypatch):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return _FakePopen(stdout=b"")

    monkeypatch.setattr(subprocess, "Popen", fake_run)
    monkeypatch.setattr(local_booter.sys, "platform", "win32")
    monkeypatch.setattr(
        local_booter.shutil,
        "which",
        lambda name: "C:/pwsh.exe" if name == "pwsh" else None,
    )

    result = asyncio.run(LocalShellComponent().exec("Get-ChildItem"))

    assert result["exit_code"] == 0
    assert calls[0][0][0] == [
        "C:/pwsh.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "Get-ChildItem",
    ]
    assert calls[0][1]["shell"] is False


@pytest.mark.asyncio
async def test_managed_shell_uses_powershell_exec_on_windows(monkeypatch, tmp_path):
    calls = []

    class FakeStdout:
        async def read(self, _limit):
            if hasattr(self, "done"):
                return b""
            self.done = True
            return b"done\n"

    class FakeProcess:
        pid = 12345
        returncode = None
        stdin = None
        stdout = FakeStdout()

        async def wait(self):
            self.returncode = 0
            return 0

    async def fake_exec(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess()

    monkeypatch.setattr(local_booter.sys, "platform", "win32")
    monkeypatch.setattr(
        local_booter.shutil,
        "which",
        lambda name: "pwsh" if name == "pwsh" else None,
    )
    monkeypatch.setattr(local_booter.asyncio, "create_subprocess_exec", fake_exec)

    result = await LocalShellComponent().exec_managed(
        "Get-ChildItem",
        owner_id="owner-a",
        cwd=str(tmp_path),
        allowed_root=str(tmp_path),
        yield_time_ms=5_000,
    )

    assert result["status"] == "completed"
    assert result["stdout"] == "done\n"
    assert calls[0][0] == (
        "pwsh",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "Get-ChildItem",
    )
    assert "creationflags" in calls[0][1]


def test_managed_shell_captures_output_and_supports_incremental_poll(tmp_path):
    async def scenario() -> None:
        shell = LocalShellComponent(session_ttl_seconds=60)
        result = await shell.exec_managed(
            _python_command("print('managed-output')"),
            owner_id="umo-a",
            sender_id="sender-a",
            cwd=str(tmp_path),
            allowed_root=str(tmp_path),
            yield_time_ms=30_000,
        )
        assert result["status"] == "completed"
        assert "managed-output" in result["stdout"]
        assert result["session_closed"] is True
        await shell.shutdown_sessions()

    asyncio.run(scenario())


def test_managed_shell_owner_isolation_and_write(tmp_path):
    async def scenario() -> None:
        shell = LocalShellComponent(session_ttl_seconds=60)
        result = await shell.exec_managed(
            _python_command(
                "import sys; line=sys.stdin.readline(); print('got:'+line.strip(), flush=True)"
            ),
            owner_id="umo-a",
            sender_id="sender-a",
            cwd=str(tmp_path),
            allowed_root=str(tmp_path),
            yield_time_ms=0,
        )
        session_id = result["session_id"]
        with pytest.raises(ValueError):
            await shell.poll_session(
                owner_id="umo-b",
                sender_id="sender-b",
                session_id=session_id,
            )
        await shell.write_session(
            owner_id="umo-a",
            sender_id="sender-a",
            session_id=session_id,
            chars="hello\n",
        )
        polled = await shell.poll_session(
            owner_id="umo-a",
            sender_id="sender-a",
            session_id=session_id,
            yield_time_ms=5_000,
        )
        assert "got:hello" in polled["stdout"]
        await shell.shutdown_sessions()

    asyncio.run(scenario())


def test_managed_shell_rejects_cwd_outside_allowed_workspace(tmp_path):
    async def scenario() -> None:
        shell = LocalShellComponent()
        with pytest.raises(PermissionError, match="outside the allowed workspace"):
            await shell.exec_managed(
                "pwd",
                owner_id="owner",
                cwd=str(tmp_path / "outside"),
                allowed_root=str(tmp_path / "allowed"),
                yield_time_ms=0,
            )

    asyncio.run(scenario())


def test_managed_shell_enforces_session_count_and_shutdown(tmp_path):
    async def scenario() -> None:
        shell = LocalShellComponent(max_sessions=1, session_ttl_seconds=60)
        first = await shell.exec_managed(
            _python_command("import time; time.sleep(10)"),
            owner_id="owner",
            cwd=str(tmp_path),
            allowed_root=str(tmp_path),
            yield_time_ms=0,
        )
        assert first["status"] == "running"
        with pytest.raises(ValueError, match="session limit"):
            await shell.exec_managed(
                "echo second",
                owner_id="owner",
                cwd=str(tmp_path),
                allowed_root=str(tmp_path),
                yield_time_ms=0,
            )
        await shell.shutdown_sessions()
        assert (await shell.list_sessions("owner"))["sessions"] == []

    asyncio.run(scenario())


def test_managed_shell_timeout_marks_session_and_terminates(tmp_path):
    async def scenario() -> None:
        shell = LocalShellComponent(session_ttl_seconds=60)
        result = await shell.exec_managed(
            _python_command("import time; time.sleep(5)"),
            owner_id="owner",
            cwd=str(tmp_path),
            allowed_root=str(tmp_path),
            timeout=1,
            yield_time_ms=0,
        )
        polled = await shell.poll_session(
            owner_id="owner",
            session_id=result["session_id"],
            yield_time_ms=3_000,
        )
        assert polled["status"] == "timed_out"
        await shell.shutdown_sessions()

    asyncio.run(scenario())


def test_managed_shell_output_is_bounded(tmp_path):
    async def scenario() -> None:
        shell = LocalShellComponent(
            max_output_bytes=32,
            session_ttl_seconds=60,
        )
        result = await shell.exec_managed(
            _python_command("print('x' * 100, flush=True)"),
            owner_id="owner",
            cwd=str(tmp_path),
            allowed_root=str(tmp_path),
            yield_time_ms=5_000,
            max_output_chars=1000,
        )
        assert len(result["stdout"].encode()) <= 32
        # The reader can terminate the process at the quota boundary, but a
        # short-lived command may win the race and exit normally.  The quota
        # invariant is the bounded output, not one particular exit status.
        assert result["status"] in {"completed", "terminated", "failed"}
        await shell.shutdown_sessions()

    asyncio.run(scenario())


@pytest.mark.asyncio
async def test_managed_shell_poll_propagates_cancellation_and_shutdowns(tmp_path):
    shell = LocalShellComponent(session_ttl_seconds=60)
    started = await shell.exec_managed(
        _python_command("import time; time.sleep(10)"),
        owner_id="owner",
        runtime_id="runtime-a",
        sender_id="sender-a",
        cwd=str(tmp_path),
        allowed_root=str(tmp_path),
        yield_time_ms=0,
    )
    poll_task = asyncio.create_task(
        shell.poll_session(
            owner_id="owner",
            runtime_id="runtime-a",
            sender_id="sender-a",
            session_id=started["session_id"],
            yield_time_ms=30_000,
        )
    )
    await asyncio.sleep(0)
    poll_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await poll_task

    await shell.shutdown_sessions()
    assert (await shell.list_sessions("owner", runtime_id="runtime-a"))[
        "sessions"
    ] == []
