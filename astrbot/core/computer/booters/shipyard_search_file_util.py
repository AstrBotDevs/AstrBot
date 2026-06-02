from __future__ import annotations

import shlex
from typing import Any

from ..olayer import ShellComponent

_MAX_SEARCH_LINE_COLUMNS = 1000


def _truncate_long_lines(text: str) -> str:
    output_lines: list[str] = []
    for line in text.splitlines(keepends=True):
        line_ending = ""
        line_body = line
        if line.endswith("\r\n"):
            line_body = line[:-2]
            line_ending = "\r\n"
        elif line.endswith("\n") or line.endswith("\r"):
            line_body = line[:-1]
            line_ending = line[-1]

        if len(line_body) > _MAX_SEARCH_LINE_COLUMNS:
            line_body = line_body[:_MAX_SEARCH_LINE_COLUMNS]

        output_lines.append(f"{line_body}{line_ending}")
    return "".join(output_lines)


def _build_rg_command(
    *,
    pattern: str,
    path: str,
    glob: str | None,
    after_context: int | None,
    before_context: int | None,
) -> list[str]:
    command = [
        "rg",
        "--color=never",
        "-n",
        "--max-columns",
        str(_MAX_SEARCH_LINE_COLUMNS),
        "-e",
        pattern,
    ]
    if glob:
        command.extend(["-g", glob])
    if after_context is not None:
        command.extend(["-A", str(after_context)])
    if before_context is not None:
        command.extend(["-B", str(before_context)])
    command.extend(["--", path])
    return command


def _build_grep_command(
    *,
    pattern: str,
    path: str,
    glob: str | None,
    after_context: int | None,
    before_context: int | None,
) -> list[str]:
    command = ["grep", "-R", "-H", "-n", "-e", pattern]
    if glob:
        command.append(f"--include={glob}")
    if after_context is not None:
        command.extend(["-A", str(after_context)])
    if before_context is not None:
        command.extend(["-B", str(before_context)])
    command.extend(["--", path])
    return command


def _quote_command(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def build_search_command(
    *,
    pattern: str,
    path: str,
    glob: str | None,
    after_context: int | None,
    before_context: int | None,
) -> str:
    rg_command = _quote_command(
        _build_rg_command(
            pattern=pattern,
            path=path,
            glob=glob,
            after_context=after_context,
            before_context=before_context,
        )
    )
    grep_command = _quote_command(
        _build_grep_command(
            pattern=pattern,
            path=path,
            glob=glob,
            after_context=after_context,
            before_context=before_context,
        )
    )
    return (
        "if command -v rg >/dev/null 2>&1; then "
        f"{rg_command}; "
        "elif command -v grep >/dev/null 2>&1; then "
        f"{grep_command}; "
        "else "
        "echo 'Neither rg nor grep is available in the sandbox.' >&2; "
        "exit 127; "
        "fi"
    )


async def search_files_via_shell(
    shell: ShellComponent,
    *,
    pattern: str,
    path: str | None = None,
    glob: str | None = None,
    after_context: int | None = None,
    before_context: int | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    command = build_search_command(
        pattern=pattern,
        path=path or ".",
        glob=glob,
        after_context=after_context,
        before_context=before_context,
    )
    result = await shell.exec(command, timeout=timeout)
    stdout = _truncate_long_lines(str(result.get("stdout", "") or ""))
    stderr = str(result.get("stderr", "") or "")
    exit_code = result.get("exit_code")
    if exit_code in (0, None):
        return {"success": True, "content": stdout}
    if exit_code == 1:
        return {"success": True, "content": ""}
    return {
        "success": False,
        "content": "",
        "error": stderr or f"command exited with code {exit_code}",
        "exit_code": exit_code,
    }
