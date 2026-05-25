"""
Robust file editing engine for AstrBot, inspired by opencode's multi-strategy replacer chain.

Implements 9 fallback replacers to handle LLM-generated edits that may have:
- indentation drift
- whitespace normalization issues
- escape sequence mismatches (\\n vs actual newline)
- trailing/leading whitespace differences
- block-level fuzzy matching via Levenshtein similarity

Author: AstrBot Agent Harness Development Expert
Date: 2026-05-18 (refactored)
"""

from __future__ import annotations

import asyncio
import difflib
import os
import weakref
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

Replacer = Callable[[str, str], Iterator[str]]

# File-level locks to prevent concurrent edits on the same file.
# Use WeakValueDictionary so locks for deleted files can be garbage-collected.
_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()
_locks_lock = asyncio.Lock()


async def _get_lock(path: str) -> asyncio.Lock:
    """Get or create an asyncio.Lock for the given file path."""
    resolved = str(Path(path).resolve())
    async with _locks_lock:
        lock = _locks.get(resolved)
        if lock is None:
            lock = asyncio.Lock()
            _locks[resolved] = lock
        return lock


# ---------------------------------------------------------------------------
# Line-ending / BOM helpers (mirrors opencode src/tool/edit.ts)
# ---------------------------------------------------------------------------


def _normalize_line_endings(text: str) -> str:
    """
    Normalize actual CRLF line endings to LF.

    ONLY handles real carriage-return + newline sequences (\\r\\n bytes).
    Does NOT interpret escape sequences — literal \\n in file content
    (e.g. Python string literals) must be preserved as-is.

    Escape sequence handling for search strings is done by the
    _escape_normalized_replacer in the replacer chain.
    """
    return text.replace("\r\n", "\n")




def _detect_line_ending(text: str) -> Literal["\n", "\r\n"]:
    return "\r\n" if "\r\n" in text else "\n"


def _convert_to_line_ending(text: str, ending: Literal["\n", "\r\n"]) -> str:
    if ending == "\n":
        return text
    # Convert standalone \n to \r\n, but avoid converting existing \r\n to \r\r\n
    # by first normalizing any existing \r\n to \n, then converting all \n to \r\n
    text = text.replace("\r\n", "\n")
    return text.replace("\n", "\r\n")


# ---------------------------------------------------------------------------
# Levenshtein distance (for BlockAnchorReplacer)
# ---------------------------------------------------------------------------


def _levenshtein(a: str, b: str) -> int:
    if a == "" or b == "":
        return max(len(a), len(b))
    # Use a single row DP to reduce memory
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        curr = [i]
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            cost = 0 if ai == b[j - 1] else 1
            curr.append(min(curr[-1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[len(b)]


# ---------------------------------------------------------------------------
# Escape helpers
# ---------------------------------------------------------------------------


def _unescape(s: str) -> str:
    """
    Unescape common escape sequences in a string.

    Handles: \\n, \\t, \\r, \\b, \\f, \\v, \\\\, \\", \\', \\`, \\$
    Also handles \\xNN hex and \\uNNNN unicode escapes.
    """
    result = []
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt == "n":
                result.append("\n")
            elif nxt == "t":
                result.append("\t")
            elif nxt == "r":
                result.append("\r")
            elif nxt == "b":
                result.append("\b")
            elif nxt == "f":
                result.append("\f")
            elif nxt == "v":
                result.append("\v")
            elif nxt == "x" and i + 3 < len(s):
                # \xNN hex escape
                try:
                    val = int(s[i + 2 : i + 4], 16)
                    result.append(chr(val))
                    i += 4
                    continue
                except ValueError:
                    result.append(s[i])
                    result.append(nxt)
            elif nxt == "u" and i + 5 < len(s):
                # \uNNNN unicode escape
                try:
                    val = int(s[i + 2 : i + 6], 16)
                    result.append(chr(val))
                    i += 6
                    continue
                except ValueError:
                    result.append(s[i])
                    result.append(nxt)
            elif nxt in ("'", '"', "`", "\\", "$"):
                result.append(nxt)
            else:
                # Unknown escape: preserve both characters
                result.append(s[i])
                result.append(nxt)
            i += 2
        else:
            result.append(s[i])
            i += 1
    return "".join(result)


# ---------------------------------------------------------------------------
# Replacer implementations
# ---------------------------------------------------------------------------


def _simple_replacer(content: str, find: str) -> Iterator[str]:
    """Exact match."""
    if not find:
        return
    yield find


def _escape_normalized_replacer(content: str, find: str) -> Iterator[str]:
    """
    Handle escaped sequences like \\n, \\t in the find string.

    This replacer tries two approaches:
    1. Unescape the find string and look for it in content
    2. If find contains literal backslash sequences, try matching content
       blocks after unescaping them

    Results are deduplicated to avoid yielding the same block twice.
    """
    if not find:
        return

    yielded = set()

    # Approach 1: unescape find and search in content
    unescaped_find = _unescape(find)
    if unescaped_find != find and unescaped_find in content:
        yielded.add(unescaped_find)
        yield unescaped_find

    # Approach 2: if find contains literal backslash sequences,
    # try matching against content blocks after unescaping
    if "\\" in find:
        lines = content.split("\n")
        find_lines = unescaped_find.split("\n")
        for i in range(len(lines) - len(find_lines) + 1):
            block = "\n".join(lines[i : i + len(find_lines)])
            if block not in yielded and _unescape(block) == unescaped_find:
                yielded.add(block)
                yield block


def _line_trimmed_replacer(content: str, find: str) -> Iterator[str]:
    """Match blocks where each line matches after trim."""
    if not find:
        return
    original_lines = content.split("\n")
    search_lines = find.split("\n")
    if search_lines and search_lines[-1] == "":
        search_lines.pop()
    if not search_lines:
        return
    for i in range(len(original_lines) - len(search_lines) + 1):
        if all(
            original_lines[i + j].strip() == search_lines[j].strip()
            for j in range(len(search_lines))
        ):
            yield "\n".join(original_lines[i : i + len(search_lines)])


def _block_anchor_replacer(content: str, find: str) -> Iterator[str]:
    """
    Use first and last line as anchors, then use Levenshtein similarity on middle lines.
    Single candidate threshold: 0.0 (accept if anchors match)
    Multiple candidates threshold: 0.3 (pick best)
    """
    if not find:
        return
    original_lines = content.split("\n")
    search_lines = find.split("\n")
    if len(search_lines) < 3:
        return
    if search_lines and search_lines[-1] == "":
        search_lines.pop()
    if len(search_lines) < 3:
        return

    first_anchor = search_lines[0].strip()
    last_anchor = search_lines[-1].strip()
    search_block_size = len(search_lines)

    candidates: list[tuple[int, int]] = []
    for i, line in enumerate(original_lines):
        if line.strip() != first_anchor:
            continue
        for j in range(i + 2, len(original_lines)):
            if original_lines[j].strip() == last_anchor:
                candidates.append((i, j))
                break

    if not candidates:
        return

    def _similarity(start: int, end: int) -> float:
        actual_size = end - start + 1
        lines_to_check = min(search_block_size - 2, actual_size - 2)
        if lines_to_check <= 0:
            return 1.0
        sim = 0.0
        for k in range(1, lines_to_check + 1):
            if start + k >= len(original_lines) or k >= len(search_lines) - 1:
                break
            ol = original_lines[start + k].strip()
            sl = search_lines[k].strip()
            max_len = max(len(ol), len(sl))
            if max_len == 0:
                continue
            dist = _levenshtein(ol, sl)
            sim += (1 - dist / max_len) / lines_to_check
        return sim

    if len(candidates) == 1:
        start, end = candidates[0]
        if _similarity(start, end) >= 0.0:
            yield "\n".join(original_lines[start : end + 1])
        return

    best_match: tuple[int, int] | None = None
    max_sim = -1.0
    for start, end in candidates:
        sim = _similarity(start, end)
        if sim > max_sim:
            max_sim = sim
            best_match = (start, end)

    if max_sim >= 0.3 and best_match:
        start, end = best_match
        yield "\n".join(original_lines[start : end + 1])


def _whitespace_normalized_replacer(content: str, find: str) -> Iterator[str]:
    """Collapse all whitespace sequences to a single space before matching."""
    if not find:
        return

    def _norm(t: str) -> str:
        return " ".join(t.split())

    normalized_find = _norm(find)
    if not normalized_find:
        return

    # Single-line matches
    for line in content.split("\n"):
        if _norm(line) == normalized_find:
            yield line

    # Multi-line block matches
    lines = content.split("\n")
    find_lines = find.split("\n")
    if len(find_lines) > 1:
        for i in range(len(lines) - len(find_lines) + 1):
            block = "\n".join(lines[i : i + len(find_lines)])
            if _norm(block) == normalized_find:
                yield block


def _indentation_flexible_replacer(content: str, find: str) -> Iterator[str]:
    """
    Match blocks where removing common indentation makes them equal to find.

    Important: yields the ORIGINAL block (with original indentation),
    not the de-indented version. This preserves the file's indentation
    during replacement.
    """
    if not find:
        return

    def _remove_indent(text: str) -> str:
        lines = text.split("\n")
        non_empty = [ln for ln in lines if ln.strip()]
        if not non_empty:
            return text
        min_indent = min(
            len(ln) - len(ln.lstrip()) for ln in non_empty if ln.strip()
        )
        return "\n".join(
            ln[min_indent:] if ln.strip() else ln for ln in lines
        )

    normalized_find = _remove_indent(find)
    content_lines = content.split("\n")
    find_lines = find.split("\n")
    for i in range(len(content_lines) - len(find_lines) + 1):
        block = "\n".join(content_lines[i : i + len(find_lines)])
        if _remove_indent(block) == normalized_find:
            yield block


def _trimmed_boundary_replacer(content: str, find: str) -> Iterator[str]:
    """Match if the trimmed version of find exists in content."""
    if not find:
        return
    trimmed = find.strip()
    if trimmed == find:
        return
    if trimmed in content:
        yield trimmed

    lines = content.split("\n")
    find_lines = find.split("\n")
    for i in range(len(lines) - len(find_lines) + 1):
        block = "\n".join(lines[i : i + len(find_lines)])
        if block.strip() == trimmed:
            yield block


def _context_aware_replacer(content: str, find: str) -> Iterator[str]:
    """
    Use first and last line as context anchors, accept if >= 50% of middle lines match.
    """
    if not find:
        return
    find_lines = find.split("\n")
    if len(find_lines) < 3:
        return
    if find_lines and find_lines[-1] == "":
        find_lines.pop()
    if len(find_lines) < 3:
        return

    first_line = find_lines[0].strip()
    last_line = find_lines[-1].strip()
    content_lines = content.split("\n")

    for i, line in enumerate(content_lines):
        if line.strip() != first_line:
            continue
        for j in range(i + 2, len(content_lines)):
            if content_lines[j].strip() != last_line:
                continue
            block_lines = content_lines[i : j + 1]
            if len(block_lines) != len(find_lines):
                continue
            matching = 0
            total_nonempty = 0
            for k in range(1, len(block_lines) - 1):
                bl = block_lines[k].strip()
                fl = find_lines[k].strip()
                if bl or fl:
                    total_nonempty += 1
                    if bl == fl:
                        matching += 1
            if total_nonempty == 0 or matching / total_nonempty >= 0.5:
                yield "\n".join(block_lines)
                return  # Only first match
            break


def _multi_occurrence_replacer(content: str, find: str) -> Iterator[str]:
    """Yield all exact matches (used with replace_all)."""
    if not find:
        return
    start = 0
    while True:
        idx = content.find(find, start)
        if idx == -1:
            break
        yield find
        start = idx + len(find)


# Ordered chain: most specific first, most lenient last.
# Escape-normalized is placed early because it handles a common LLM issue
# (using \\n instead of actual newlines) before more aggressive fuzzy matchers.
_REPLACERS: list[Replacer] = [
    _simple_replacer,
    _escape_normalized_replacer,
    _line_trimmed_replacer,
    _block_anchor_replacer,
    _whitespace_normalized_replacer,
    _indentation_flexible_replacer,
    _trimmed_boundary_replacer,
    _context_aware_replacer,
    _multi_occurrence_replacer,
]


# ---------------------------------------------------------------------------
# Core replace function
# ---------------------------------------------------------------------------


def robust_replace(
    content: str,
    old_string: str,
    new_string: str,
    *,
    replace_all: bool = False,
) -> tuple[str, int]:
    """
    Replace old_string with new_string using the multi-strategy replacer chain.

    Returns:
        A tuple of (new_content, replacements_count).

    Raises:
        ValueError: If old_string cannot be found, or if multiple non-unique
                    matches are found (when replace_all=False).
    """
    if old_string == new_string:
        raise ValueError("No changes to apply: old_string and new_string are identical.")

    not_found = True

    for replacer in _REPLACERS:
        matches = list(replacer(content, old_string))
        if not matches:
            continue

        # Collect all unique match positions
        match_positions: list[tuple[int, str]] = []
        for match in matches:
            start = 0
            while True:
                idx = content.find(match, start)
                if idx == -1:
                    break
                # Avoid duplicate positions from overlapping matches
                if not any(pos <= idx < pos + len(m) for pos, m in match_positions):
                    match_positions.append((idx, match))
                start = idx + 1

        if not match_positions:
            continue

        not_found = False

        if replace_all:
            # Replace all occurrences, from end to start to preserve indices
            new_content = content
            replacements = 0
            for idx, match in sorted(match_positions, key=lambda x: x[0], reverse=True):
                new_content = new_content[:idx] + new_string + new_content[idx + len(match):]
                replacements += 1
            return new_content, replacements

        # Single replacement mode: require exactly one match
        if len(match_positions) == 1:
            idx, match = match_positions[0]
            return content[:idx] + new_string + content[idx + len(match):], 1

        # Multiple matches found in single-replacement mode: continue to next replacer
        # to try a more specific strategy
        continue

    if not_found:
        raise ValueError(
            "Could not find oldString in the file. It must match exactly, "
            "including whitespace, indentation, and line endings. "
            "Try providing more surrounding context to make the match unique."
        )
    raise ValueError(
        "Found multiple matches for oldString. Provide more surrounding context "
        "to make the match unique, or use replace_all=True to change every instance."
    )


# ---------------------------------------------------------------------------
# Edit result model
# ---------------------------------------------------------------------------


@dataclass
class EditResult:
    success: bool
    replacements: int = 0
    diff: str = ""
    error: str = ""
    old_content: str = ""
    new_content: str = ""


# ---------------------------------------------------------------------------
# Async file edit with locking and line-ending preservation
# ---------------------------------------------------------------------------


async def edit_file(
    path: str,
    old_string: str,
    new_string: str,
    *,
    replace_all: bool = False,
    encoding: str = "utf-8",
) -> EditResult:
    """
    Edit a file using the robust multi-strategy replacer.

    Features:
    - File-level asyncio lock prevents concurrent edits
    - Preserves original line endings (\n vs \r\n)
    - Preserves BOM if present
    - Returns unified diff of changes
    """
    lock = await _get_lock(path)
    async with lock:
        try:
            # Read file
            raw_bytes = await asyncio.to_thread(_read_file_bytes, path)
            has_bom = raw_bytes.startswith(b"\xef\xbb\xbf")
            if has_bom:
                raw_bytes = raw_bytes[3:]

            old_content = raw_bytes.decode(encoding)
            original_ending = _detect_line_ending(old_content)

            # Normalize for matching: ONLY normalize actual CRLF line endings.
            # Escape sequence handling (\n vs actual newline, \t vs tab, etc.)
            # is deferred to the _escape_normalized_replacer in the replacer chain.
            # We must NOT call _normalize_escapes here — it would convert literal
            # \n in search strings to actual newlines, preventing matching of
            # literal \n in file content (e.g. Python string literals).
            normalized_old = _normalize_line_endings(old_string)
            normalized_new = _normalize_line_endings(new_string)

            # Normalize file content to LF for matching (replacers work on LF)
            normalized_content = _normalize_line_endings(old_content)
            # Perform replacement
            new_content, replacements = robust_replace(
                normalized_content, normalized_old, normalized_new, replace_all=replace_all
            )

            # Convert back to original line endings
            if original_ending == "\r\n":
                new_content = _convert_to_line_ending(new_content, "\r\n")

            # Re-add BOM if present
            write_bytes = b""
            if has_bom:
                write_bytes += b"\xef\xbb\xbf"
            write_bytes += new_content.encode(encoding)

            # Write file
            await asyncio.to_thread(_write_file_bytes, path, write_bytes)

            # Generate unified diff
            diff = _generate_unified_diff(
                path, old_content.splitlines(keepends=True),
                path, new_content.splitlines(keepends=True)
            )

            return EditResult(
                success=True,
                replacements=replacements,
                diff=diff,
                old_content=old_content,
                new_content=new_content,
            )

        except Exception as exc:
            return EditResult(
                success=False,
                error=str(exc),
            )


def _read_file_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _write_file_bytes(path: str, data: bytes) -> None:
    # Ensure parent directory exists
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def _generate_unified_diff(
    old_path: str,
    old_lines: list[str],
    new_path: str,
    new_lines: list[str],
) -> str:
    """Generate a compact unified diff."""
    diff = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=old_path,
            tofile=new_path,
            lineterm="",
        )
    )
    return "".join(diff)
