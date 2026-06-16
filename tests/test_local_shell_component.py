from __future__ import annotations

import asyncio
import subprocess
import sys
import time

from astrbot.core.computer.booters import local as local_booter
from astrbot.core.computer.booters.local import LocalShellComponent


class _FakePopen:
    """Minimal stand-in for the subprocess.Popen context manager used in exec()."""

    def __init__(self, stdout: bytes, stderr: bytes = b"", returncode: int = 0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self.pid = 4321

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def communicate(self, timeout=None):
        _ = timeout
        return self._stdout, self._stderr


def test_local_shell_component_decodes_utf8_output(monkeypatch):
    def fake_popen(*args, **kwargs):
        _ = args, kwargs
        return _FakePopen(stdout="技能内容".encode())

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    result = asyncio.run(LocalShellComponent().exec("dummy"))

    assert result["stdout"] == "技能内容"
    assert result["stderr"] == ""
    assert result["exit_code"] == 0


def test_local_shell_component_prefers_utf8_before_windows_locale(
    monkeypatch,
):
    def fake_popen(*args, **kwargs):
        _ = args, kwargs
        return _FakePopen(stdout="技能内容".encode())

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
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
    def fake_popen(*args, **kwargs):
        _ = args, kwargs
        return _FakePopen(stdout="微博热搜".encode("gbk"))

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
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
    def fake_popen(*args, **kwargs):
        _ = args, kwargs
        return _FakePopen(stdout=b"\xffabc")

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(local_booter.os, "name", "posix", raising=False)
    monkeypatch.setattr(
        local_booter.locale,
        "getpreferredencoding",
        lambda _do_setlocale=False: "utf-8",
    )

    result = asyncio.run(LocalShellComponent().exec("dummy"))

    assert result["stdout"] == "\ufffdabc"


def test_local_shell_component_timeout_returns_promptly():
    # Spawn a long-running child through the shell. On Windows the shell keeps
    # running while the child holds the captured stdout/stderr pipes open, so a
    # plain subprocess.run(timeout=...) blocks until the child exits and the
    # timeout is never enforced. The component must kill the whole process tree
    # and surface the timeout within the configured window.
    sleeper = f'"{sys.executable}" -c "import time; time.sleep(30)"'
    start = time.monotonic()
    timed_out = False
    try:
        asyncio.run(LocalShellComponent().exec(sleeper, timeout=2))
    except subprocess.TimeoutExpired:
        timed_out = True
    elapsed = time.monotonic() - start

    assert timed_out, "expected the shell command to time out"
    assert elapsed < 15, f"shell timeout was not enforced (took {elapsed:.1f}s)"
