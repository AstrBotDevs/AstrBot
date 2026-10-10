"""Keep QQ display equations outside native Markdown list scroll containers."""

import bisect
import re
from dataclasses import dataclass

from markdown_it import MarkdownIt

_QUOTE = re.compile(r"^(?:[ ]{0,3}>[ ]?)*")
_LIST_MARKER = re.compile(r"^[ \t]*(?P<marker>[-+*]|\d{1,9}[.)])[ \t]+")
_MATH_START = re.compile(
    r"^[ \t]*(?:(?:[-+*]|\d{1,9}[.)])[ \t]+)?(?P<delimiter>\$\$|\\\[)"
)
_PARSER = MarkdownIt("commonmark")


@dataclass(frozen=True)
class _ListItem:
    start: int
    end: int
    indent: int
    marker: str
    marker_column: int
    quote_depth: int


@dataclass(frozen=True)
class _MathBlock:
    start: int
    end: int
    prefix: int
    quote: str
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


def _split_quote(line: str) -> tuple[str, str]:
    """Split a blockquote prefix (``> `` or ``> > ``) from a line."""
    quote = _QUOTE.match(line).group()
    return quote, line[len(quote) :]


def _indent_width(line: str) -> int:
    return len(line[: len(line) - len(line.lstrip(" \t"))].expandtabs(4))


def _dedent_container(line: str, columns: int) -> str:
    prefix = line[: len(line) - len(line.lstrip(" \t"))]
    return prefix.expandtabs(4)[columns:] + line[len(prefix) :]


def _reopen_containers(line: str, items: list[_ListItem]) -> str | None:
    """Re-enter the list items a lifted equation closed, keeping each later
    line at its original nesting depth instead of flattening it to the root.
    """
    quote, rest = _split_quote(line)
    width = _indent_width(rest)
    items = [item for item in items if width >= item.indent]
    if not items:
        return None
    markers = []
    previous = 0
    for item in items:
        padding = item.indent - item.marker_column - len(item.marker)
        if item.marker_column < previous or not 1 <= padding <= 4:
            return None
        markers.append(
            " " * (item.marker_column - previous) + item.marker + " " * padding
        )
        previous = item.indent
    return quote + "".join(markers) + _dedent_container(rest, items[-1].indent)


def normalize_qq_list_math(text: str) -> str:
    """Lift standalone display math out of lists without rewriting its TeX.

    QQ can stop scrolling a list's equation before its right edge. Blank
    lines and removal of the list container's indentation make the equation
    a top-level block (inside any enclosing blockquote). The list items the
    equation closed are reopened on the next line, so later paragraphs,
    nested lists and sibling items keep their original nesting depth. Parse
    the original containers to protect code blocks.
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
            quote, rest = _split_quote(lines[start])
            marker = _LIST_MARKER.match(rest)
            if marker:
                items.append(
                    _ListItem(
                        start,
                        end,
                        len(marker.group().expandtabs(4)),
                        marker["marker"],
                        len(rest[: marker.start("marker")].expandtabs(4)),
                        quote.count(">"),
                    )
                )

    if not items:
        return text

    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    blocks: list[_MathBlock] = []
    line_number = 0
    while line_number < len(lines):
        quote, rest = _split_quote(lines[line_number])
        opening = _MATH_START.match(rest)
        ancestors = tuple(
            item
            for item in items
            if item.start <= line_number < item.end
            and item.quote_depth == quote.count(">")
        )
        if line_number in protected or not opening or not ancestors:
            line_number += 1
            continue
        delimiter = opening["delimiter"]
        closing = "$$" if delimiter == "$$" else "\\]"
        end = _find_closing(
            text,
            closing,
            offsets[line_number] + len(quote) + opening.end(),
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
            _MathBlock(
                line_number,
                last_line,
                len(quote) + opening.start("delimiter"),
                quote,
                ancestors,
            )
        )
        line_number = last_line + 1

    if not blocks:
        return text

    starts = {block.start: block for block in blocks}
    reopened: dict[int, str] = {}
    for block in blocks:
        following = next(
            (
                index
                for index in range(block.end + 1, len(lines))
                if _split_quote(lines[index])[1].strip()
            ),
            None,
        )
        if following is None or following in starts:
            continue
        line = _reopen_containers(
            lines[following],
            [item for item in block.ancestors if following < item.end],
        )
        if line is not None:
            reopened[following] = line

    newline = "\r\n" if "\r\n" in text else "\n"
    output: list[str] = []
    for index, line in enumerate(lines):
        block = starts.get(index)
        if block is not None:
            if output and _split_quote(output[-1])[1].strip():
                output.append(block.quote.rstrip() + newline)
            line = block.quote + line[block.prefix :]
        output.append(reopened.get(index, line))
        ending = next((b for b in blocks if b.end == index), None)
        if (
            ending is not None
            and index + 1 < len(lines)
            and _split_quote(lines[index + 1])[1].strip()
        ):
            output.append(ending.quote.rstrip() + newline)
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
