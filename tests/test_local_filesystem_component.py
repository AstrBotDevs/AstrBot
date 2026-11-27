from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

from astrbot.core.astr_agent_runtime.computer import process_sandbox
from astrbot.core.astr_agent_runtime.computer.booters import local as local_booter
from astrbot.core.astr_agent_runtime.computer.booters.local import (
    LocalFileSystemComponent,
)


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

    def fake_search(command, **kwargs):
        calls.append((command, kwargs))
        return {"success": True, "content": "src\\demo.py:4:needle\n"}

    monkeypatch.setattr(local_booter.shutil, "which", lambda _: r"C:\tools\rg.exe")
    monkeypatch.setattr(local_booter, "run_search", fake_search)
    result = asyncio.run(
        LocalFileSystemComponent().search_files(
            "needle",
            path=r"C:\workspace",
            glob="*.py",
            after_context=2,
            before_context=1,
            max_results=5,
            max_output_bytes=4096,
            timeout=7,
        )
    )
    assert result == {"success": True, "content": "src\\demo.py:4:needle\n"}
    command, options = calls[0]
    assert command == [
        r"C:\tools\rg.exe",
        "--color=never",
        "-n",
        "--max-columns",
        "1000",
        "--max-columns-preview",
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
    ]
    assert options["max_results"] == 5
    assert options["max_output_bytes"] == 4096
    assert options["timeout"] == 7
    assert options["has_context"] is True


@pytest.fixture(params=[False, True], ids=["rg", "fallback"])
def local_search_backend(request, monkeypatch):
    if request.param:
        monkeypatch.setattr(local_booter.shutil, "which", lambda _: None)
    elif local_booter.shutil.which("rg") is None:
        pytest.skip("ripgrep executable unavailable")
    return request.param


def test_local_file_system_component_treats_rg_no_match_as_success(
    tmp_path, local_search_backend
):
    target = tmp_path / "text.txt"
    target.write_text("available\n", encoding="utf-8")
    result = asyncio.run(
        LocalFileSystemComponent().search_files("missing", str(target))
    )
    assert result == {"success": True, "content": ""}


def test_local_file_system_component_truncates_rg_long_lines_after_search(
    tmp_path, local_search_backend
):
    target = tmp_path / "large.txt"
    target.write_text("x" * (2 * 1024 * 1024) + "needle\n", encoding="utf-8")
    result = asyncio.run(LocalFileSystemComponent().search_files("needle", str(target)))
    assert result == {"success": True, "content": "1:" + "x" * 998 + "\n"}


def test_local_file_system_component_requires_rg_on_python_314(monkeypatch):
    monkeypatch.setattr(local_booter.shutil, "which", lambda _: None)
    monkeypatch.setattr(local_booter.sys, "version_info", (3, 14))
    result = asyncio.run(LocalFileSystemComponent().search_files("needle"))
    assert result == {
        "success": False,
        "content": "",
        "error": (
            "The ripgrep (rg) executable is required for file search "
            "on Python 3.14 or later because python-ripgrep 0.0.8 is incompatible."
        ),
    }


def test_local_file_system_component_prefers_rg_before_314(monkeypatch):
    monkeypatch.setattr(local_booter.sys, "version_info", (3, 13))
    monkeypatch.setattr(local_booter.shutil, "which", lambda _: "/bin/rg")
    calls = []

    def fake_search(command, **kwargs):
        calls.append(command)
        return {"success": True, "content": "技能内容\n"}

    monkeypatch.setattr(local_booter, "run_search", fake_search)
    result = asyncio.run(LocalFileSystemComponent().search_files("skill"))
    assert result == {"success": True, "content": "技能内容\n"}
    assert calls[0][0] == "/bin/rg"


@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize("limited", [False, True])
def test_local_file_system_component_runs_restricted_search_in_read_only_sandbox(
    monkeypatch, tmp_path, fallback, limited
):
    import json

    sandbox_calls = []

    class FakeSandbox:
        def run(self, argv, spec, **kwargs):
            sandbox_calls.append((argv, spec, kwargs))
            return process_sandbox.SandboxRunResult(
                returncode=0,
                stdout=b"target.txt:1:needle\npartial"
                if limited
                else b"target.txt:1:needle\n",
                stderr=b"",
                stdout_limited=limited,
            )

    monkeypatch.setattr(
        local_booter.shutil, "which", lambda _: None if fallback else "/usr/bin/rg"
    )
    monkeypatch.setattr(local_booter, "create_process_sandbox", lambda: FakeSandbox())
    result = asyncio.run(
        LocalFileSystemComponent().search_files(
            "needle",
            path=str(tmp_path / "target.txt"),
            sandboxed=True,
            sandbox_root=str(tmp_path),
            max_results=10,
            max_output_bytes=4096,
            timeout=5,
        )
    )
    assert result["success"] is True
    assert result["content"] == "target.txt:1:needle\n"
    assert result.get("truncated", False) is limited
    argv, spec, options = sandbox_calls[0]
    assert argv[:4] == [sys.executable, "-I", "-S", "-c"]
    arguments = json.loads(argv[-1])
    assert arguments["max_results"] == 10
    assert arguments["max_output_bytes"] == 4096
    assert arguments["timeout"] == 5
    assert spec.workspace == tmp_path
    assert spec.workspace_writable is False
    assert options == {"timeout": 5, "output_limit": 4096}


def test_local_file_system_component_handles_search_timeout(monkeypatch):
    monkeypatch.setattr(local_booter.shutil, "which", lambda _: "/bin/rg")

    def fake_search(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(local_booter, "run_search", fake_search)
    result = asyncio.run(LocalFileSystemComponent().search_files("needle"))
    assert result == {
        "success": False,
        "content": "",
        "error": "File search timed out after 30 seconds.",
    }


def test_local_search_glob_context_groups_and_bounds(tmp_path, local_search_backend):
    (tmp_path / "target.py").write_text(
        "before\nneedle\nafter\nspace\nspace\nbefore2\nneedle\nafter2\n",
        encoding="utf-8",
    )
    (tmp_path / "excluded.txt").write_text("needle\n", encoding="utf-8")
    result = asyncio.run(
        LocalFileSystemComponent().search_files(
            "needle",
            str(tmp_path),
            glob="*.py",
            after_context=1,
            before_context=1,
            max_results=1,
        )
    )
    assert result["success"] is True
    assert result["truncation_reason"] == "max_results"
    assert len(result["content"].splitlines()) == 3
    assert "2:needle" in result["content"]
    assert "3-after" in result["content"]


def test_local_search_byte_limit_and_invalid_regex(tmp_path, local_search_backend):
    target = tmp_path / "text.txt"
    target.write_text("needle\n" * 500, encoding="utf-8")
    result = asyncio.run(
        LocalFileSystemComponent().search_files(".", str(target), max_output_bytes=128)
    )
    assert result["success"] is True
    assert result["truncation_reason"] == "max_output_bytes"
    assert len(result["content"].encode()) <= 128
    result = asyncio.run(LocalFileSystemComponent().search_files("[", str(target)))
    assert result["success"] is False
    assert result["error"]


def test_local_fallback_hung_regex_is_killed(monkeypatch, tmp_path):
    monkeypatch.setattr(local_booter.shutil, "which", lambda _: None)
    target = tmp_path / "text.txt"
    target.write_text("a" * 500 + "!", encoding="utf-8")
    result = asyncio.run(
        LocalFileSystemComponent().search_files("(a+)+$", str(target), timeout=0.2)
    )
    assert result == {
        "success": False,
        "content": "",
        "error": "File search timed out after 0.2 seconds.",
    }


def test_local_search_broad_pattern_has_bounded_python_memory(
    tmp_path, local_search_backend
):
    import tracemalloc

    workspace = tmp_path / "node_modules"
    workspace.mkdir()
    for index in range(40):
        (workspace / f"{index:03}.js").write_text("payload\n" * 200, encoding="utf-8")
    (workspace / "bundle.map").write_text("x" * (2 * 1024 * 1024), encoding="utf-8")
    tracemalloc.start()
    try:
        result = asyncio.run(
            LocalFileSystemComponent().search_files(
                ".", str(workspace), max_results=10, max_output_bytes=1024 * 1024
            )
        )
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result["success"]
    assert result["truncation_reason"] == "max_results"
    assert len(result["content"].splitlines()) == 10
    assert peak < 10 * 1024 * 1024


@pytest.mark.parametrize("budget", [128, 4096])
def test_restricted_search_executes_embedded_runner_with_limits(
    monkeypatch, tmp_path, local_search_backend, budget
):
    class TestSandbox:
        def run(self, argv, spec, *, timeout, output_limit):
            assert spec.workspace_writable is False
            completed = subprocess.run(
                argv, cwd=spec.workspace, capture_output=True, timeout=timeout
            )
            # Deliberately don't enforce the parent capture limit: this test
            # verifies the standalone runner's own bounds, not a canned reply.
            assert len(completed.stdout) <= output_limit
            return process_sandbox.SandboxRunResult(
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )

    target = tmp_path / "matches.txt"
    target.write_text("needle\n" * 1000, encoding="utf-8")
    monkeypatch.setattr(local_booter, "create_process_sandbox", lambda: TestSandbox())
    result = asyncio.run(
        LocalFileSystemComponent().search_files(
            ".",
            str(target),
            sandboxed=True,
            sandbox_root=str(tmp_path),
            max_results=10,
            max_output_bytes=budget,
        )
    )
    assert result["success"]
    assert result["truncated"]
    assert len(result["content"].splitlines()) <= 10
    assert len(result["content"].encode()) <= budget
    if budget == 4096:
        assert len(result["content"].splitlines()) == 10


@pytest.mark.parametrize("character", ["中", "😀"])
def test_local_rg_preserves_multibyte_character_prefix(tmp_path, character):
    if local_booter.shutil.which("rg") is None:
        pytest.skip("ripgrep executable unavailable")
    target = tmp_path / "unicode.txt"
    target.write_text(character * 2000 + "needle\n", encoding="utf-8")
    result = asyncio.run(LocalFileSystemComponent().search_files("needle", str(target)))
    assert result == {"success": True, "content": "1:" + character * 998 + "\n"}
