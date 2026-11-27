from __future__ import annotations

import shlex
from typing import Any

from ..olayer import ShellComponent

_MAX_SEARCH_LINE_COLUMNS = 1000
_MAX_SEARCH_OUTPUT_BYTES = 1024 * 1024
_TRUNCATION_MARKER = "__ASTRBOT_SEARCH_TRUNCATED__:"


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
        "--max-columns-preview",
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
    command = ["grep", "-R", "-I", "-H", "-n", "-e", pattern]
    if glob:
        command.append(f"--include={glob}")
    if after_context is not None:
        command.extend(["-A", str(after_context)])
    if before_context is not None:
        command.extend(["-B", str(before_context)])
    command.extend(["--", path])
    return command


def _quote_command(command: list[str]) -> str:
    return shlex.join(command)


def build_search_command(
    *,
    pattern: str,
    path: str,
    glob: str | None,
    after_context: int | None,
    before_context: int | None,
    max_results: int | None = None,
    max_output_bytes: int | None = None,
) -> str:
    """Build a POSIX search command with bounded transport output.

    Args:
        pattern: Regular expression passed as a search argument.
        path: Search root or explicit file.
        glob: Optional file filter.
        after_context: Number of trailing context lines.
        before_context: Number of leading context lines.
        max_results: Maximum global result groups, or no group limit.
        max_output_bytes: Maximum captured bytes, defaulting to one MiB.

    Returns:
        Shell command that preserves the search exit status and reports limits.
    """
    byte_limit = (
        _MAX_SEARCH_OUTPUT_BYTES if max_output_bytes is None else max_output_bytes
    )
    if byte_limit < 1 or (max_results is not None and max_results < 1):
        raise ValueError("Search output limits must be greater than zero.")
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
    search_command = (
        "if command -v rg >/dev/null 2>&1; then "
        f"{rg_command}; "
        "elif command -v grep >/dev/null 2>&1; then "
        f"{grep_command}; "
        "else "
        "echo 'Neither rg nor grep is available in the sandbox.' >&2; "
        "(exit 127); "
        "fi"
    )
    has_context = (after_context or 0) > 0 or (before_context or 0) > 0
    # Cap the stream before awk reads records: grep may output a multi-MiB line.
    # The status file avoids relying on non-POSIX pipefail and distinguishes an
    # intentional SIGPIPE from regex or filesystem failures.
    limiter = r"""
{
    line = $0
    sub(/\r$/, "", line)
    if (context && line == "--") {
        boundary = 1
        separator = $0
        next
    }
    if (line !~ /^[[:space:]]*$/) {
        if (!context || boundary || groups == 0) {
            if (limit > 0 && groups >= limit) {
                print "max_results" > flag
                exit
            }
            if (context && groups > 0 && separator != "") print separator
            groups++
            boundary = 0
            separator = ""
        }
    }
    print
}
"""
    return (
        "( search_tmp=$(mktemp -d) || exit 2; "
        "trap 'rm -rf \"$search_tmp\"' 0; "
        'mkfifo "$search_tmp/errors" || exit 2; '
        '{ head -c 65536; cat >/dev/null; } < "$search_tmp/errors" '
        '> "$search_tmp/stderr" & error_reader=$!; '
        "{ search_status=0; "
        f"{search_command} || search_status=$?; "
        'printf \'%s\' "$search_status" > "$search_tmp/status"; '
        '} 2> "$search_tmp/errors" | '
        f'head -c {byte_limit + 1} | tee "$search_tmp/captured" | '
        f"LC_ALL=C awk -v limit={max_results or 0} "
        f"-v context={int(has_context)} "
        f'-v flag="$search_tmp/truncated" {shlex.quote(limiter)}; '
        "limiter_status=$?; "
        'wait "$error_reader"; cat "$search_tmp/stderr" >&2; '
        'if [ "$limiter_status" -ne 0 ]; then exit "$limiter_status"; fi; '
        'if [ ! -f "$search_tmp/truncated" ] && '
        f'[ "$(wc -c < "$search_tmp/captured")" -gt {byte_limit} ]; then '
        "printf '%s' max_output_bytes > \"$search_tmp/truncated\"; fi; "
        'if [ -f "$search_tmp/truncated" ]; then '
        f"printf '\\n{_TRUNCATION_MARKER}%s\\n' "
        '"$(cat "$search_tmp/truncated")" >&2; fi; '
        'search_status=$(cat "$search_tmp/status") || exit 2; '
        'exit "$search_status" )'
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
    max_results: int | None = None,
    max_output_bytes: int | None = None,
) -> dict[str, Any]:
    command = build_search_command(
        pattern=pattern,
        path=path or ".",
        glob=glob,
        after_context=after_context,
        before_context=before_context,
        max_results=max_results,
        max_output_bytes=max_output_bytes,
    )
    result = await shell.exec(command, timeout=timeout)
    raw_stdout = str(result.get("stdout", "") or "")
    stdout = _truncate_long_lines(raw_stdout)
    stderr = str(result.get("stderr", "") or "")
    exit_code = result.get("exit_code")
    truncation_reason = None
    error_lines = []
    for line in stderr.splitlines():
        if line.startswith(_TRUNCATION_MARKER):
            truncation_reason = line.removeprefix(_TRUNCATION_MARKER)
        else:
            error_lines.append(line)
    byte_limit = (
        _MAX_SEARCH_OUTPUT_BYTES if max_output_bytes is None else max_output_bytes
    )
    if not truncation_reason and len(raw_stdout.encode("utf-8")) > byte_limit:
        truncation_reason = "max_output_bytes"
    if (exit_code in (0, None) and result.get("success") is not False) or (
        truncation_reason and exit_code in (0, 1, 141, -13)
    ):
        response: dict[str, Any] = {"success": True, "content": stdout}
        if truncation_reason:
            content = stdout.encode("utf-8")[:byte_limit].decode(
                "utf-8", errors="ignore"
            )
            if truncation_reason == "max_output_bytes" and (
                (after_context or 0) > 0 or (before_context or 0) > 0
            ):
                # A byte ceiling can interrupt context. Keep only groups whose
                # closing separator was observed before the stream ended.
                groups = content.split("\n--\n")
                content = "\n--\n".join(groups[:-1])
                if content and not content.endswith("\n"):
                    content += "\n"
            response["content"] = content
            response["truncated"] = True
            response["truncation_reason"] = truncation_reason
        return response
    if exit_code == 1:
        return {"success": True, "content": ""}
    return {
        "success": False,
        "content": "",
        "error": "\n".join(error_lines).strip()
        or stdout
        or f"command exited with code {exit_code}",
        "exit_code": exit_code,
    }
