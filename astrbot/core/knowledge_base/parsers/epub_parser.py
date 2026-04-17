"""EPUB document parser."""

import re

from astrbot.core.knowledge_base.parsers.base import BaseParser, ParseResult

_EPUB_METADATA_LINE_RE = re.compile(r"^\*\*[A-Za-z][A-Za-z0-9 _-]*:\*\* .+$")
_EPUB_TOC_LINE_RE = re.compile(
    r"^\s*(?:[-*+]|\d+\.)\s+\[[^\]]+\]\([^)]+\.x?html(?:#[^)]+)?\)\s*$"
)
_EPUB_INTERNAL_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+\.x?html(?:#[^)]+)?)\)")
_EPUB_FOOTNOTE_LABEL_RE = re.compile(r"^\s*(?:\\?\*)?\d+[A-Za-z]?\s*$")
_EPUB_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_EPUB_EMPTY_IMAGE_LINK_RE = re.compile(
    r"\[\s*\]\([^)]+\.(?:png|jpe?g|gif|webp|svg)(?:#[^)]+)?\)",
    re.IGNORECASE,
)


def _strip_epub_metadata_and_toc(markdown: str) -> str:
    lines = markdown.replace("\r\n", "\n").split("\n")
    index = 0

    while index < len(lines) and not lines[index].strip():
        index += 1

    metadata_start = index
    while index < len(lines) and _EPUB_METADATA_LINE_RE.match(lines[index].strip()):
        index += 1

    if index > metadata_start:
        while index < len(lines) and not lines[index].strip():
            index += 1

    toc_start = index
    while index < len(lines) and _EPUB_TOC_LINE_RE.match(lines[index].strip()):
        index += 1

    if index - toc_start >= 2:
        while index < len(lines) and not lines[index].strip():
            index += 1
    else:
        index = toc_start

    return "\n".join(lines[index:]).strip()


def _strip_epub_internal_footnote_links(markdown: str) -> str:
    def replace_link(match: re.Match[str]) -> str:
        label = match.group(1).strip()
        href = match.group(2).lower()
        if "#filepos" in href and _EPUB_FOOTNOTE_LABEL_RE.match(label):
            return ""
        return label

    return _EPUB_INTERNAL_LINK_RE.sub(replace_link, markdown)


def _sanitize_epub_markdown(markdown: str) -> str:
    lines = markdown.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    prev_blank = True

    for raw_line in lines:
        line = _EPUB_IMAGE_RE.sub("", raw_line)
        line = _EPUB_EMPTY_IMAGE_LINK_RE.sub("", line)
        line = line.rstrip()

        if line.strip():
            out.append(line)
            prev_blank = False
        elif not prev_blank:
            out.append("")
            prev_blank = True

    return "\n".join(out).strip()


class EpubParser(BaseParser):
    """Parse EPUB files via MarkItDown."""

    async def parse(self, file_content: bytes, file_name: str) -> ParseResult:
        from .markitdown_parser import MarkitdownParser

        result = await MarkitdownParser().parse(file_content, file_name)
        return ParseResult(
            text=_sanitize_epub_markdown(
                _strip_epub_internal_footnote_links(
                    _strip_epub_metadata_and_toc(result.text),
                ),
            ),
            media=result.media,
        )
