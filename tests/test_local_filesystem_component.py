from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from astrbot.core.computer.booters import local as local_booter
from astrbot.core.computer.booters.local import LocalFileSystemComponent


def _allow_tmp_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(local_booter, "get_astrbot_root", lambda: str(tmp_path))


def test_local_file_system_component_prefers_utf8_before_windows_locale(
    monkeypatch,
    tmp_path: Path,
):
    _allow_tmp_root(monkeypatch, tmp_path)
    monkeypatch.setattr(local_booter.os, "name", "nt", raising=False)
    monkeypatch.setattr(
        local_booter.locale,
        "getpreferredencoding",
        lambda _do_setlocale=False: "cp936",
    )

    skill_path = tmp_path / "skills" / "demo.txt"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_bytes("技能内容".encode())

    result = asyncio.run(LocalFileSystemComponent().read_file(str(skill_path)))

    assert result["success"] is True
    assert result["content"] == "技能内容"


def test_local_file_system_component_falls_back_to_gbk_on_windows(
    monkeypatch,
    tmp_path: Path,
):
    _allow_tmp_root(monkeypatch, tmp_path)
    monkeypatch.setattr(local_booter.os, "name", "nt", raising=False)
    monkeypatch.setattr(
        local_booter.locale,
        "getpreferredencoding",
        lambda _do_setlocale=False: "cp1252",
    )

    skill_path = tmp_path / "skills" / "weibo-hot.txt"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_bytes("微博热搜".encode("gbk"))

    result = asyncio.run(LocalFileSystemComponent().read_file(str(skill_path)))

    assert result["success"] is True
    assert result["content"] == "微博热搜"


def test_local_file_system_component_searches_with_rg_glob_and_context(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=b"src\\demo.py:4:needle\n",
            stderr=b"",
        )

    monkeypatch.setattr(
        local_booter.shutil,
        "which",
        lambda _executable: r"C:\tools\rg.exe",
    )
    monkeypatch.setattr(local_booter.sys, "version_info", (3, 14))
    monkeypatch.setattr(local_booter.subprocess, "run", fake_run)

    result = asyncio.run(
        LocalFileSystemComponent().search_files(
            "needle",
            path=r"C:\workspace",
            glob="*.py",
            after_context=2,
            before_context=1,
        )
    )

    assert result == {"success": True, "content": "src\\demo.py:4:needle\n"}
    assert calls == [
        (
            [
                r"C:\tools\rg.exe",
                "--color=never",
                "-n",
                "-e",
                "needle",
                "-g",
                "*.py",
                "-A",
                "2",
                "-B",
                "1",
                "--",
                r"C:\workspace",
            ],
            {
                "capture_output": True,
                "timeout": 30,
            },
        )
    ]


def test_local_file_system_component_treats_rg_no_match_as_success(monkeypatch):
    monkeypatch.setattr(local_booter.shutil, "which", lambda _executable: "/bin/rg")
    monkeypatch.setattr(local_booter.sys, "version_info", (3, 14))
    monkeypatch.setattr(
        local_booter.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command,
            1,
            stdout=b"",
            stderr=b"",
        ),
    )

    result = asyncio.run(LocalFileSystemComponent().search_files("missing"))

    assert result == {"success": True, "content": ""}


def test_local_file_system_component_truncates_rg_long_lines_after_search(
    monkeypatch,
):
    long_line = b"result.py:1:" + (b"x" * 1200) + b"\n"
    monkeypatch.setattr(local_booter.shutil, "which", lambda _executable: "/bin/rg")
    monkeypatch.setattr(local_booter.sys, "version_info", (3, 14))
    monkeypatch.setattr(
        local_booter.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout=long_line,
            stderr=b"",
        ),
    )

    result = asyncio.run(LocalFileSystemComponent().search_files("x"))

    assert result["success"] is True
    assert result["content"] == long_line.decode()[:1000] + "\n"


def test_local_file_system_component_requires_rg_on_python_314(monkeypatch):
    calls = []

    monkeypatch.setattr(local_booter.shutil, "which", lambda _executable: None)
    monkeypatch.setattr(local_booter.sys, "version_info", (3, 14))
    monkeypatch.setattr(
        local_booter.subprocess,
        "run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    result = asyncio.run(LocalFileSystemComponent().search_files("needle"))

    assert result == {
        "success": False,
        "content": "",
        "error": (
            "The ripgrep (rg) executable is required for file search on Python 3.14 "
            "or later because python-ripgrep 0.0.8 is incompatible."
        ),
    }
    assert calls == []


def test_local_file_system_component_preserves_python_ripgrep_before_314(monkeypatch):
    calls = []

    def fake_search(**kwargs):
        calls.append(kwargs)
        return ["技能内容\n"]

    monkeypatch.setattr(local_booter.sys, "version_info", (3, 13))
    monkeypatch.setattr(local_booter, "search", fake_search)
    monkeypatch.setattr(
        local_booter.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("subprocess should not be used"),
    )

    result = asyncio.run(
        LocalFileSystemComponent().search_files(
            "skill",
            path="skills",
            glob="*.md",
            after_context=3,
            before_context=2,
        )
    )

    assert result == {"success": True, "content": "技能内容\n"}
    assert calls == [
        {
            "patterns": ["skill"],
            "paths": ["skills"],
            "globs": ["*.md"],
            "after_context": 3,
            "before_context": 2,
            "line_number": True,
        }
    ]


def test_local_file_system_component_handles_search_timeout(monkeypatch):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(local_booter.shutil, "which", lambda _executable: "/bin/rg")
    monkeypatch.setattr(local_booter.sys, "version_info", (3, 14))
    monkeypatch.setattr(local_booter.subprocess, "run", fake_run)

    result = asyncio.run(LocalFileSystemComponent().search_files("needle"))

    assert result == {
        "success": False,
        "content": "",
        "error": "File search timed out after 30 seconds.",
    }
