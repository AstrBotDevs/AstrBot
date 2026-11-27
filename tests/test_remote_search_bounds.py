from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.astr_agent_runtime.computer.booters.cua import (
    CuaFileSystemComponent,
    _PosixShellFileSystem,
)
from astrbot.core.astr_agent_runtime.computer.booters.shipyard import (
    ShipyardFileSystemWrapper,
)
from astrbot.core.astr_agent_runtime.computer.booters.shipyard_neo import (
    NeoFileSystemComponent,
)
from astrbot.core.astr_agent_runtime.computer.booters.shipyard_search_file_util import (
    build_search_command,
    search_files_via_shell,
)


@pytest.fixture
def posix_shell(tmp_path):
    executable = shutil.which("sh")
    if executable is None and (git := shutil.which("git")):
        candidate = Path(git).resolve().parent.parent / "bin" / "sh.exe"
        if candidate.is_file():
            executable = str(candidate)
    if executable is None:
        pytest.skip("POSIX shell is not installed")

    class LocalTestShell:
        def __init__(self):
            self.results = []
            self.force_grep = False

        async def exec(self, command, timeout=30):
            if self.force_grep:
                command = command.replace(
                    "if command -v rg >/dev/null 2>&1", "if false"
                )
            env = dict(os.environ)
            env["TMPDIR"] = tmp_path.as_posix()
            completed = await asyncio.to_thread(
                subprocess.run,
                [executable, "-c", command],
                capture_output=True,
                timeout=timeout,
                env=env,
                cwd=tmp_path,
            )
            result = {
                "stdout": completed.stdout.decode("utf-8", errors="replace"),
                "stderr": completed.stderr.decode("utf-8", errors="replace"),
                "exit_code": completed.returncode,
            }
            self.results.append(result)
            return result

    return LocalTestShell()


@pytest.mark.asyncio
async def test_remote_search_stops_globally_and_cleans_temp_directory(
    posix_shell, tmp_path
):
    root = tmp_path / "input"
    root.mkdir()
    for index in range(8):
        (root / f"{index}.txt").write_text("needle\n" * 100, encoding="utf-8")

    result = await search_files_via_shell(
        posix_shell,
        pattern="needle",
        path=root.as_posix(),
        max_results=3,
        max_output_bytes=4096,
    )

    assert result["success"], result
    assert result["truncated"]
    assert result["truncation_reason"] == "max_results"
    assert len(result["content"].splitlines()) == 3
    assert len(posix_shell.results[-1]["stdout"].encode()) <= 4096
    assert list(tmp_path.iterdir()) == [root]


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["rg", "grep"])
async def test_remote_context_finishes_last_selected_group(
    posix_shell, tmp_path, backend
):
    if backend == "rg" and shutil.which("rg") is None:
        pytest.skip("ripgrep is not installed")
    posix_shell.force_grep = backend == "grep"
    file = tmp_path / "context.txt"
    file.write_text(
        "before\nneedle\nafter\nskip\nskip\nbefore2\nneedle\nafter2\n",
        encoding="utf-8",
    )
    result = await search_files_via_shell(
        posix_shell,
        pattern="needle",
        path=file.name,
        before_context=1,
        after_context=1,
        max_results=1,
    )
    assert result["success"]
    assert result["truncation_reason"] == "max_results"
    assert result["content"].splitlines() == (
        ["1-before", "2:needle", "3-after"]
        if backend == "rg"
        else ["context.txt-1-before", "context.txt:2:needle", "context.txt-3-after"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["rg", "grep"])
async def test_remote_byte_cap_bounds_large_lines(posix_shell, tmp_path, backend):
    if backend == "rg" and shutil.which("rg") is None:
        pytest.skip("ripgrep is not installed")
    posix_shell.force_grep = backend == "grep"
    file = tmp_path / "long.txt"
    file.write_text("x" * (2 * 1024 * 1024) + "\n", encoding="utf-8")
    result = await search_files_via_shell(
        posix_shell, pattern=".", path=file.name, max_output_bytes=80
    )
    assert result["success"]
    assert result["truncation_reason"] == "max_output_bytes"
    assert len(result["content"].encode()) <= 80
    prefix = "1:" if backend == "rg" else "long.txt:1:"
    assert result["content"] == prefix.ljust(80, "x")
    assert len(posix_shell.results[-1]["stdout"].encode()) <= 82


@pytest.mark.asyncio
async def test_remote_rg_preview_keeps_the_line_prefix(posix_shell, tmp_path):
    if shutil.which("rg") is None:
        pytest.skip("ripgrep is not installed")
    file = tmp_path / "long.txt"
    file.write_text("x" * (2 * 1024 * 1024) + "\n", encoding="utf-8")
    result = await search_files_via_shell(
        posix_shell, pattern=".", path=file.as_posix()
    )
    assert result == {"success": True, "content": "1:" + "x" * 998 + "\n"}


@pytest.mark.asyncio
@pytest.mark.parametrize("character", ["\u4f60", "\U0001f600"])
async def test_remote_rg_preview_counts_unicode_characters(
    posix_shell, tmp_path, character
):
    if shutil.which("rg") is None:
        pytest.skip("ripgrep is not installed")
    file = tmp_path / "unicode.txt"
    file.write_bytes((character * 2000 + "\n").encode("utf-8"))
    result = await search_files_via_shell(posix_shell, pattern=".", path=file.name)
    assert result == {"success": True, "content": "1:" + character * 998 + "\n"}


@pytest.mark.asyncio
async def test_remote_result_limit_stops_the_producer(posix_shell, tmp_path):
    marker = tmp_path / "producer_completed"

    class InfiniteShell:
        async def exec(self, command, timeout=30):
            command = command.replace("if command -v rg >/dev/null 2>&1", "if true")
            producer = (
                'i=0; while [ "$i" -lt 1000000 ]; do '
                "printf '1:%080d\\n' 0 || exit $?; i=$((i + 1)); done; "
                "touch producer_completed"
            )
            return await posix_shell.exec(
                f"rg() {{ sh -c {shlex.quote(producer)}; }}; " + command,
                timeout=timeout,
            )

    started = time.monotonic()
    result = await search_files_via_shell(
        InfiniteShell(), pattern=".", max_results=1, max_output_bytes=4096, timeout=10
    )
    assert result["success"], result
    assert result["truncation_reason"] == "max_results"
    assert len(result["content"].splitlines()) == 1
    assert not marker.exists()
    assert time.monotonic() - started < 10


@pytest.mark.asyncio
async def test_remote_invalid_regex_is_not_hidden_by_pipeline(posix_shell, tmp_path):
    file = tmp_path / "input.txt"
    file.write_text("needle\n", encoding="utf-8")
    result = await search_files_via_shell(
        posix_shell, pattern="[", path=file.as_posix(), max_output_bytes=10
    )
    assert result["success"] is False
    assert result["error"]


@pytest.mark.asyncio
async def test_remote_diagnostics_are_drained_without_becoming_results(
    posix_shell, tmp_path
):
    class DiagnosticShell:
        async def exec(self, command, timeout=30):
            command = command.replace("if command -v rg >/dev/null 2>&1", "if true")
            return await posix_shell.exec(
                "rg() { head -c 100000 /dev/zero | tr '\\000' x >&2; "
                "printf '1:needle\\n'; }; " + command,
                timeout=timeout,
            )

    result = await search_files_via_shell(
        DiagnosticShell(), pattern="needle", max_results=1, max_output_bytes=32
    )
    assert result == {"success": True, "content": "1:needle\n"}
    assert len(posix_shell.results[-1]["stderr"].encode()) == 65536


@pytest.mark.asyncio
async def test_remote_no_matches_preserves_return_shape(posix_shell, tmp_path):
    file = tmp_path / "input.txt"
    file.write_text("haystack\n", encoding="utf-8")
    result = await search_files_via_shell(
        posix_shell, pattern="needle", path=file.as_posix()
    )
    assert result == {"success": True, "content": ""}


@pytest.mark.asyncio
async def test_remote_grep_fallback_is_bounded_and_skips_binary(posix_shell, tmp_path):
    posix_shell.force_grep = True
    binary = tmp_path / "binary.dat"
    binary.write_bytes(b"\x00needle\n" * 1000)
    assert await search_files_via_shell(
        posix_shell, pattern="needle", path=binary.as_posix()
    ) == {"success": True, "content": ""}

    text = tmp_path / "input.txt"
    text.write_text("needle\n" * 10000, encoding="utf-8")
    result = await search_files_via_shell(
        posix_shell,
        pattern="needle",
        path=text.as_posix(),
        max_results=2,
        max_output_bytes=1024,
    )
    assert result["success"]
    assert result["truncation_reason"] == "max_results"
    assert len(result["content"].splitlines()) == 2

    text.write_text("needle" * 400000, encoding="utf-8")
    result = await search_files_via_shell(
        posix_shell, pattern="needle", path=text.as_posix(), max_output_bytes=80
    )
    assert result["success"]
    assert result["truncation_reason"] == "max_output_bytes"
    assert len(result["content"].encode()) <= 80
    assert len(posix_shell.results[-1]["stdout"].encode()) <= 82


@pytest.mark.asyncio
async def test_remote_byte_cap_drops_an_incomplete_context_group(posix_shell, tmp_path):
    file = tmp_path / "context.txt"
    file.write_text("needle\n" + "context\n" * 100, encoding="utf-8")
    result = await search_files_via_shell(
        posix_shell,
        pattern="needle",
        path=file.as_posix(),
        after_context=100,
        max_results=1,
        max_output_bytes=80,
    )
    assert result == {
        "success": True,
        "content": "",
        "truncated": True,
        "truncation_reason": "max_output_bytes",
    }


def test_remote_commands_quote_arguments_and_skip_binary_grep():
    command = build_search_command(
        pattern="$(touch unsafe);'",
        path="-file with space",
        glob="*.txt",
        after_context=0,
        before_context=0,
        max_results=3,
        max_output_bytes=512,
    )
    assert "--max-columns 1000 --max-columns-preview" in command
    assert "grep -R -I -H -n" in command
    assert "head -c 513" in command
    assert "-- '-file with space'" in command
    assert "pipefail" not in command


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["rg", "grep"])
async def test_remote_pattern_is_not_executed_by_the_shell(
    posix_shell, tmp_path, backend
):
    if backend == "rg" and shutil.which("rg") is None:
        pytest.skip("ripgrep is not installed")
    posix_shell.force_grep = backend == "grep"
    marker = tmp_path / "injected"
    file = tmp_path / "input.txt"
    file.write_text("harmless\n", encoding="utf-8")
    result = await search_files_via_shell(
        posix_shell,
        pattern="$(touch injected);'",
        path=file.name,
    )
    assert result == {"success": True, "content": ""}
    assert not marker.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("booter", ["shipyard", "neo", "cua", "posix"])
async def test_remote_booters_accept_and_forward_search_limits(booter):
    shell = SimpleNamespace(
        exec=AsyncMock(return_value={"stdout": "1:needle\n", "exit_code": 0})
    )
    if booter == "shipyard":
        fs = ShipyardFileSystemWrapper(SimpleNamespace(), shell)
    elif booter == "neo":
        fs = NeoFileSystemComponent(SimpleNamespace(), shell)
    elif booter == "cua":
        fs = object.__new__(CuaFileSystemComponent)
        fs._fallback = _PosixShellFileSystem(shell, "linux")
    else:
        fs = _PosixShellFileSystem(shell, "linux")

    assert await fs.search_files("needle") == {
        "success": True,
        "content": "1:needle\n",
    }
    result = await fs.search_files(
        "needle", max_results=3, max_output_bytes=512, timeout=7
    )
    assert result == {"success": True, "content": "1:needle\n"}
    command = shell.exec.call_args.args[0]
    assert "limit=3" in command
    assert "head -c 513" in command
    assert shell.exec.call_args.kwargs["timeout"] == 7


@pytest.mark.asyncio
async def test_remote_truncation_marker_can_make_sdk_success_flag_false():
    shell = SimpleNamespace(
        exec=AsyncMock(
            return_value={
                "stdout": "1:needle\n",
                "stderr": "__ASTRBOT_SEARCH_TRUNCATED__:max_results\n",
                "exit_code": 0,
                "success": False,
            }
        )
    )
    result = await search_files_via_shell(shell, pattern="needle", max_results=1)
    assert result == {
        "success": True,
        "content": "1:needle\n",
        "truncated": True,
        "truncation_reason": "max_results",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("exit_code", [141, -13])
async def test_remote_truncation_does_not_hide_real_errors(exit_code):
    shell = SimpleNamespace(
        exec=AsyncMock(
            return_value={
                "stdout": "1:needle\n",
                "stderr": "real error\n__ASTRBOT_SEARCH_TRUNCATED__:max_results\n",
                "exit_code": exit_code,
            }
        )
    )
    result = await search_files_via_shell(shell, pattern="needle", max_results=1)
    assert result == {
        "success": False,
        "content": "",
        "error": "real error",
        "exit_code": exit_code,
    }
