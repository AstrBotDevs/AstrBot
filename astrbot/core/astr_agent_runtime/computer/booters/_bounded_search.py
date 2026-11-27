"""Bounded, killable file-search fallback for installations without ripgrep.

This module deliberately uses only the standard library so Local can execute its
source in the read-only process sandbox. Python regular expressions cover common
grep patterns; unsupported syntax reports an error instead of omitting matches.
"""

from __future__ import annotations

import codecs
import fnmatch
import json
import locale
import mmap
import re
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any, BinaryIO

_TEXT_LINE_BYTES = 64 * 1024
_MAX_OUTPUT_BYTES = 1024 * 1024
_MAX_LINE_COLUMNS = 1000


def _candidate_files(root: Path, glob: str | None):
    """Walk regular files without following directory or file symlinks.

    Args:
        root: Explicit file or directory being searched.
        glob: Optional ripgrep-style include or exclude glob.

    Yields:
        Paths of candidate files, honoring ordinary gitignore rules.

    Raises:
        OSError: If the requested path cannot be read.
        ValueError: If an ignore file cannot be processed within the budget.
    """
    import os

    def matches(relative: str, pattern: str) -> bool:
        brace = re.search(r"\{([^{}]+)\}", pattern)
        if brace:
            return any(
                matches(
                    relative,
                    pattern[: brace.start()] + alternative + pattern[brace.end() :],
                )
                for alternative in brace.group(1).split(",")
            )
        anchored = pattern.startswith("/")
        pattern = pattern.lstrip("/")
        if "/" not in pattern and not anchored:
            return any(
                fnmatch.fnmatchcase(part, pattern) for part in relative.split("/")
            )
        # Match path segments separately: fnmatch's '*' also accepts '/',
        # whereas ripgrep reserves cross-directory matching for '**'.
        segments = relative.split("/")
        parts = pattern.split("/")
        positions = {0}
        for part in parts:
            if part == "**":
                positions = set(
                    range(min(positions, default=len(segments) + 1), len(segments) + 1)
                )
            else:
                positions = {
                    index + 1
                    for index in positions
                    if index < len(segments)
                    and fnmatch.fnmatchcase(segments[index], part)
                }
            if not positions:
                return False
        return len(segments) in positions

    if root.is_file():
        yield root
        return
    if not root.is_dir():
        raise FileNotFoundError(f"Search path does not exist: {root}")

    rules: list[tuple[Path, str]] = []
    rule_bytes = 0

    def walk(directory: Path):
        nonlocal rule_bytes
        previous_count = len(rules)
        previous_bytes = rule_bytes
        try:
            for name in (".gitignore", ".ignore", ".rgignore"):
                ignore_path = directory / name
                if not ignore_path.is_file() or ignore_path.is_symlink():
                    continue
                with ignore_path.open("rb") as source:
                    raw_rules = source.read(_TEXT_LINE_BYTES + 1)
                if len(raw_rules) > _TEXT_LINE_BYTES:
                    raise ValueError(
                        "Large ignore files require the ripgrep (rg) executable."
                    )
                for raw_rule in raw_rules.decode(
                    "utf-8", errors="replace"
                ).splitlines():
                    rule = raw_rule.rstrip()
                    if rule and not rule.startswith("#"):
                        rule_bytes += len(rule.encode("utf-8")) + 160
                        if rule_bytes > _MAX_OUTPUT_BYTES:
                            raise ValueError(
                                "The accumulated ignore rules require the ripgrep (rg) executable."
                            )
                        rules.append((directory, rule))
            with os.scandir(directory) as entries:
                for entry in entries:
                    if (
                        entry.is_symlink()
                        or entry.name == ".git"
                        or getattr(
                            entry.stat(follow_symlinks=False), "st_file_attributes", 0
                        )
                        & 0x400  # FILE_ATTRIBUTE_REPARSE_POINT also excludes junctions.
                    ):
                        continue
                    entry_path = Path(entry.path)
                    try:
                        glob_path = (
                            entry_path.resolve().relative_to(Path.cwd()).as_posix()
                        )
                    except ValueError:
                        glob_path = entry_path.as_posix()
                    is_dir = entry.is_dir(follow_symlinks=False)
                    ignored = False
                    for base, rule in rules:
                        negative = rule.startswith("!")
                        pattern = rule[1:] if negative else rule
                        directory_only = pattern.endswith("/")
                        if directory_only and not is_dir:
                            continue
                        if matches(
                            entry_path.relative_to(base).as_posix(), pattern.rstrip("/")
                        ):
                            ignored = not negative
                    if not is_dir and glob and not glob.startswith("!"):
                        # Command-line includes override ignore files, as with rg.
                        if matches(glob_path, glob):
                            ignored = False
                    if ignored:
                        continue
                    # An explicit positive glob opts hidden files into the search.
                    if entry.name.startswith(".") and (
                        not glob or glob.startswith("!")
                    ):
                        continue
                    if is_dir:
                        yield from walk(entry_path)
                    elif entry.is_file(follow_symlinks=False):
                        if glob:
                            negative = glob.startswith("!")
                            if (
                                matches(glob_path, glob[1:] if negative else glob)
                                == negative
                            ):
                                continue
                        yield entry_path

        finally:
            del rules[previous_count:]
            rule_bytes = previous_bytes

    yield from walk(root)


def run_search(options: dict[str, Any], output: BinaryIO) -> int:
    """Write a bounded grep result without loading whole files or long lines.

    Args:
        options: Search pattern, path, glob, context, budgets and timeout.
        output: Binary stream receiving UTF-8 grep output.

    Returns:
        Exit status: zero for matches, one for no matches, or three when a
        result or byte budget ended the search. The caller enforces a process
        timeout as well, since Python's regex engine cannot be interrupted.

    Raises:
        ValueError: For invalid options or syntax requiring ripgrep.
        TimeoutError: If the wall-clock deadline expires.
        OSError: If a candidate file cannot be read.
    """
    pattern = str(options["pattern"])
    if re.search(r"\[:[A-Za-z]+:\]", pattern) or re.search(
        r"(?<!\\)(?:\\\\)*\\[zU]", pattern
    ):
        raise ValueError(
            "This Rust-specific pattern requires the ripgrep (rg) executable."
        )
    for character_class in re.findall(r"\[(?:\\.|[^\]\\])*\]", pattern):
        if any(operator in character_class for operator in ("&&", "~~", "--", "||")):
            raise ValueError(
                "Set operations in character classes require the ripgrep (rg) executable."
            )
    try:
        expression = re.compile(pattern)
    except re.error as exc:
        raise ValueError(
            f"Invalid or unsupported fallback regular expression: {exc}. "
            "Rust-specific syntax requires the ripgrep (rg) executable."
        ) from exc
    root = Path(options.get("path") or ".")
    after = int(options.get("after_context") or 0)
    before = int(options.get("before_context") or 0)
    max_results = options.get("max_results")
    max_bytes = min(
        int(
            options.get("max_output_bytes")
            if options.get("max_output_bytes") is not None
            else _MAX_OUTPUT_BYTES
        ),
        _MAX_OUTPUT_BYTES,
    )
    timeout = options.get("timeout", 30)
    if (
        after < 0
        or before < 0
        or max_bytes < 1
        or timeout <= 0
        or (max_results is not None and max_results < 1)
    ):
        raise ValueError(
            "Search limits must be positive and context must be nonnegative."
        )
    deadline = time.monotonic() + timeout
    has_context = bool(after or before)
    multiple_files = root.is_dir()
    groups = 0
    written = 0
    byte_expression = None
    literal_pattern = not any(character in pattern for character in r"\.^$*+?{}[]|()")
    # Repetition of groups can make Python's backtracking stack proportional
    # to a giant source line. Basic atoms/repeats use its constant-space fast
    # path; richer expressions still work on the bounded ordinary-line path.
    complex_long_pattern = re.search(r"(?<!\\)(?:\\\\)*[()|{]", pattern) is not None
    pending_group = bytearray()

    def emit(data: bytes) -> bool:
        nonlocal written
        if written + len(pending_group) + len(data) > max_bytes:
            return False
        if has_context:
            # Keep one group until its closing boundary is known. If its
            # context exceeds the byte budget, none of that partial group
            # reaches the caller, even if its before-lines fit by themselves.
            pending_group.extend(data)
        else:
            output.write(data)
            written += len(data)
        return True

    def truncated(reason: str) -> int:
        sys.stderr.write(json.dumps({"truncation_reason": reason}))
        return 3

    for candidate in _candidate_files(root, options.get("glob")):
        if time.monotonic() >= deadline:
            raise TimeoutError(f"File search timed out after {timeout} seconds.")
        with candidate.open("rb") as source:
            if not candidate.stat().st_size:
                continue
            with mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as data:
                # Probe only the usual binary prefix; checking the whole mmap
                # up front would touch every page even for a ten-line result.
                if data.find(b"\0", 0, min(8192, len(data))) >= 0:
                    continue
                previous: deque[tuple[int, bytes]] = deque()
                previous_bytes = 0
                last_emitted = 0
                last_match = 0
                line_number = 0
                start = 0
                while start < len(data):
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            f"File search timed out after {timeout} seconds."
                        )
                    end = data.find(b"\n", start)
                    if end < 0:
                        end = len(data)
                    body_end = end - 1 if end > start and data[end - 1] == 13 else end
                    if data.find(b"\0", start, body_end) >= 0:
                        break
                    line_number += 1
                    if body_end - start <= _TEXT_LINE_BYTES:
                        raw_line = data[start:body_end]
                        text = None
                        for encoding in (
                            "utf-8-sig",
                            locale.getpreferredencoding(False),
                            "gb18030",
                        ):
                            try:
                                text = raw_line.decode(encoding)
                                break
                            except (UnicodeDecodeError, LookupError):
                                pass
                        if text is None:
                            text = raw_line.decode("utf-8", errors="replace")
                        matched = expression.search(text) is not None
                        prefix = text[:_MAX_LINE_COLUMNS]
                    else:
                        # Search the mmap directly: even a multi-megabyte line
                        # only allocates a small output prefix. Text regex and
                        # byte regex have equal semantics for ASCII input.
                        ascii_line = True
                        utf8_decoder = codecs.getincrementaldecoder("utf-8")()
                        if complex_long_pattern:
                            raise ValueError(
                                "Grouped or alternating regular expressions on very "
                                "long lines require the ripgrep (rg) executable."
                            )
                        if not pattern.isascii() and not literal_pattern:
                            raise ValueError(
                                "Unicode regular expressions on very long lines "
                                "require the ripgrep (rg) executable."
                            )
                        for position in range(start, body_end, _TEXT_LINE_BYTES):
                            if time.monotonic() >= deadline:
                                raise TimeoutError(
                                    f"File search timed out after {timeout} seconds."
                                )
                            chunk = data[
                                position : min(position + _TEXT_LINE_BYTES, body_end)
                            ]
                            ascii_line = ascii_line and chunk.isascii()
                            if literal_pattern:
                                try:
                                    utf8_decoder.decode(chunk)
                                except UnicodeDecodeError as exc:
                                    raise ValueError(
                                        "Very long non-UTF-8 lines require the ripgrep (rg) executable."
                                    ) from exc
                            elif not ascii_line:
                                raise ValueError(
                                    "Non-ASCII lines larger than 65536 bytes require "
                                    "the ripgrep (rg) executable for accurate Unicode matching."
                                )
                        if literal_pattern:
                            try:
                                utf8_decoder.decode(b"", final=True)
                            except UnicodeDecodeError as exc:
                                raise ValueError(
                                    "Very long non-UTF-8 lines require the ripgrep (rg) executable."
                                ) from exc
                        if byte_expression is None:
                            try:
                                byte_expression = re.compile(pattern.encode("utf-8"))
                            except re.error as exc:
                                raise ValueError(
                                    "This pattern requires the ripgrep (rg) executable "
                                    "when searching very long lines."
                                ) from exc
                        # A memoryview slice sets the regex anchor boundary to
                        # this line without making a copy of its contents.
                        with (
                            memoryview(data) as view,
                            view[start:body_end] as line_view,
                        ):
                            matched = byte_expression.search(line_view) is not None
                        prefix = data[
                            start : min(start + _MAX_LINE_COLUMNS * 4, body_end)
                        ].decode("utf-8", errors="ignore")[:_MAX_LINE_COLUMNS]
                    delimiter = ":" if matched else "-"
                    label = f"{candidate}{delimiter}" if multiple_files else ""
                    rendered = f"{label}{line_number}{delimiter}{prefix}"[
                        :_MAX_LINE_COLUMNS
                    ]
                    line = (rendered + "\n").encode("utf-8")
                    if matched:
                        new_group = (
                            not has_context
                            or not last_emitted
                            or line_number - before > last_emitted + 1
                        )
                        if new_group:
                            if pending_group:
                                output.write(pending_group)
                                written += len(pending_group)
                                pending_group.clear()
                            if max_results is not None and groups >= max_results:
                                return truncated("max_results")
                            if has_context and groups and not emit(b"--\n"):
                                return truncated("max_output_bytes")
                            groups += 1
                        if has_context:
                            expected = max(1, line_number - before, last_emitted + 1)
                            if expected < line_number and (
                                not previous or previous[0][0] > expected
                            ):
                                return truncated("max_output_bytes")
                            for number, context_line in previous:
                                if number >= expected:
                                    if not emit(context_line):
                                        return truncated("max_output_bytes")
                                    last_emitted = number
                        if not emit(line):
                            return truncated("max_output_bytes")
                        last_emitted = line_number
                        last_match = line_number
                    elif (
                        has_context and last_match and line_number <= last_match + after
                    ):
                        if not emit(line):
                            return truncated("max_output_bytes")
                        last_emitted = line_number
                    if before:
                        previous.append((line_number, line))
                        # Account for deque/tuple/int overhead as well as text,
                        # so a huge -B over tiny lines cannot inflate memory.
                        previous_bytes += len(line) + 128
                        while len(previous) > before or previous_bytes > max(
                            max_bytes, _TEXT_LINE_BYTES
                        ):
                            _, old_line = previous.popleft()
                            previous_bytes -= len(old_line) + 128
                    start = end + 1
        if pending_group:
            output.write(pending_group)
            written += len(pending_group)
            pending_group.clear()
    return 0 if groups else 1


if __name__ == "__main__":
    try:
        status = run_search(json.loads(sys.argv[1]), sys.stdout.buffer)
    except TimeoutError as exc:
        sys.stderr.write(str(exc))
        status = 124
    except (OSError, ValueError, RecursionError, OverflowError) as exc:
        sys.stderr.write(str(exc))
        status = 2
    sys.exit(status)
