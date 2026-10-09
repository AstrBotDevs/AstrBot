"""Keep QQ display equations outside native Markdown list scroll containers."""

import bisect
import re
from dataclasses import dataclass

from markdown_it import MarkdownIt

_LIST_MARKER = re.compile(r"^[ \t]*(?:[-+*]|\d{1,9}[.)])[ \t]+")
_MATH_START = re.compile(
    r"^[ \t]*(?:(?:[-+*]|\d{1,9}[.)])[ \t]+)?(?P<delimiter>\$\$|\\\[)"
)
_PARSER = MarkdownIt("commonmark")


@dataclass(frozen=True)
class _ListItem:
    start: int
    end: int
    indent: int


@dataclass(frozen=True)
class _MathBlock:
    start: int
    end: int
    prefix: int
    ancestors: tuple[_ListItem, ...]


def _find_closing(text: str, delimiter: str, start: int, end: int) -> int:
    while (position := text.find(delimiter, start, end)) >= 0:
        previous = position - 1
        while previous >= 0 and text[previous] == "\\":
            previous -= 1
        if (position - 1 - previous) % 2 == 0:
            return position
        start = position + len(delimiter)
    return -1


def _dedent_container(line: str, columns: int) -> str:
    prefix = line[: len(line) - len(line.lstrip(" \t"))]
    return prefix.expandtabs(4)[columns:] + line[len(prefix) :]


def normalize_qq_list_math(text: str) -> str:
    """Lift standalone display math out of lists without rewriting its TeX.

    QQ can stop scrolling a list's equation before its right edge. Blank
    lines and removal of the list container's indentation make the equation
    a top-level block. Parse the original containers to protect code and to
    keep any subsequent list-item paragraphs/code correctly indented.
    """
    if "$$" not in text and "\\[" not in text:
        return text

    lines = text.splitlines(keepends=True)
    tokens = _PARSER.parse(text)
    protected: set[int] = set()
    items: list[_ListItem] = []
    for token in tokens:
        if token.map is None:
            continue
        start, end = token.map
        if token.type in {"fence", "code_block", "html_block"}:
            protected.update(range(start, end))
        elif token.type == "inline" and any(
            child.type == "code_inline"
            and ("$$" in child.content or "\\[" in child.content)
            for child in token.children or []
        ):
            # Inline-code source spans have no line maps. Leave ambiguous
            # paragraphs unchanged instead of interpreting literal examples.
            protected.update(range(start, end))
        elif token.type == "list_item_open":
            marker = _LIST_MARKER.match(lines[start])
            if marker:
                items.append(_ListItem(start, end, len(marker.group().expandtabs(4))))

    if not items:
        return text

    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    blocks: list[_MathBlock] = []
    line_number = 0
    while line_number < len(lines):
        opening = _MATH_START.match(lines[line_number])
        ancestors = tuple(
            item for item in items if item.start <= line_number < item.end
        )
        if line_number in protected or not opening or not ancestors:
            line_number += 1
            continue
        delimiter = opening["delimiter"]
        closing = "$$" if delimiter == "$$" else "\\]"
        end = _find_closing(
            text,
            closing,
            offsets[line_number] + opening.end(),
            offsets[min(item.end for item in ancestors)],
        )
        if end < 0:
            line_number += 1
            continue
        last_line = bisect.bisect_right(offsets, end) - 1
        if text[end + len(closing) : offsets[last_line + 1]].strip() or any(
            line in protected for line in range(line_number, last_line + 1)
        ):
            line_number += 1
            continue
        blocks.append(
            _MathBlock(line_number, last_line, opening.start("delimiter"), ancestors)
        )
        line_number = last_line + 1

    if not blocks:
        return text

    math_lines = {
        line for block in blocks for line in range(block.start, block.end + 1)
    }
    starts = {block.start: block for block in blocks}
    ends = {block.end for block in blocks}
    item_starts = {item.start for item in items}
    newline = "\r\n" if "\r\n" in text else "\n"
    output: list[str] = []
    for index, line in enumerate(lines):
        columns = max(
            (
                item.indent
                for block in blocks
                for item in block.ancestors
                if block.end < index < item.end
            ),
            default=0,
        )
        if index in starts:
            line = line[starts[index].prefix :]
        elif columns and index not in math_lines:
            line = _dedent_container(line, columns)
        if (index in starts or (columns and index in item_starts)) and (
            output and output[-1].strip()
        ):
            output.append(newline)
        output.append(line)
        if index in ends and index + 1 < len(lines) and lines[index + 1].strip():
            output.append(newline)
    return "".join(output)


class QQMarkdownMathState:
    """Preserve streaming deltas; normalize a complete final snapshot only."""

    def __init__(self) -> None:
        self.clear()

    def clear(self) -> None:
        self._parts: list[str] = []
        self._known_start = False

    def prepare(self, content: str, stream: dict | None) -> tuple[str, dict | None]:
        if stream is None:
            self.clear()
            return normalize_qq_list_math(content), None

        if stream.get("reset") or not stream.get("id"):
            self.clear()
            self._known_start = True
        self._parts.append(content)
        if stream.get("state") != 10:
            return content, stream

        source = "".join(self._parts)
        known_start = self._known_start
        self.clear()
        if not known_start:
            # Attaching midway through a stream must never erase its prefix.
            return content, stream
        normalized = normalize_qq_list_math(source)
        if normalized == source:
            return content, stream
        updated_stream = dict(stream)
        if stream.get("id"):
            updated_stream["reset"] = True
            # QQ restarts the sequence for a replacement snapshot. Reusing
            # the delta cursor after several frames is rejected by the API.
            updated_stream["index"] = 1
        return normalized, updated_stream
