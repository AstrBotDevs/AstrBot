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
