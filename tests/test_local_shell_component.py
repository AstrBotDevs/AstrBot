from __future__ import annotations

import asyncio
import subprocess

from astrbot.core.computer.booters import local as local_booter
from astrbot.core.computer.booters.local import (
    LocalShellComponent,
    _shell_output_encodings,
)


class _FakeCompletedProcess:
    def __init__(self, stdout: bytes, stderr: bytes = b"", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_local_shell_component_decodes_utf8_output(monkeypatch):
    def fake_run(*args, **kwargs):
        _ = args, kwargs
        return _FakeCompletedProcess(stdout="技能内容".encode())

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = asyncio.run(LocalShellComponent().exec("dummy"))

    assert result["stdout"] == "技能内容"
    assert result["stderr"] == ""
    assert result["exit_code"] == 0


def test_local_shell_component_falls_back_to_cp936(monkeypatch):
    def fake_run(*args, **kwargs):
        _ = args, kwargs
        return _FakeCompletedProcess(stdout="微博热搜".encode("gbk"))

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(local_booter.os, "name", "nt", raising=False)
    monkeypatch.setattr(
        local_booter.locale,
        "getpreferredencoding",
        lambda _do_setlocale=False: "utf-8",
    )

    result = asyncio.run(LocalShellComponent().exec("dummy"))

    assert result["stdout"] == "微博热搜"
    assert result["stderr"] == ""
    assert result["exit_code"] == 0


def test_shell_output_encodings_skip_windows_fallbacks_on_non_windows(monkeypatch):
    monkeypatch.setattr(local_booter.os, "name", "posix", raising=False)
    monkeypatch.setattr(
        local_booter.locale,
        "getpreferredencoding",
        lambda _do_setlocale=False: "utf-8",
    )

    encodings = _shell_output_encodings()

    assert encodings == ["utf-8"]


def test_shell_output_encodings_include_windows_fallbacks_on_windows(monkeypatch):
    monkeypatch.setattr(local_booter.os, "name", "nt", raising=False)
    monkeypatch.setattr(
        local_booter.locale,
        "getpreferredencoding",
        lambda _do_setlocale=False: "cp936",
    )

    encodings = _shell_output_encodings()

    assert encodings == ["utf-8", "cp936", "mbcs", "gbk", "gb18030"]
