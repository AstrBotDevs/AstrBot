"""EPUB document parser."""

from __future__ import annotations

import io
import re
from typing import Any

from astrbot.core.knowledge_base.parsers.base import BaseParser, ParseResult

_DROP_TAGS = ("script", "style")
_BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "br",
    "dd",
    "div",
    "dl",
    "dt",
    "figcaption",
    "figure",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "li",
    "main",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "ul",
}
_NAV_EPUB_TYPES = {"toc", "landmarks", "page-list"}


def _normalize_multiline_text(text: str) -> str:
    lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in text.splitlines()]
    out: list[str] = []
    prev_blank = True
    for line in lines:
        if line:
            out.append(line)
            prev_blank = False
        elif not prev_blank:
            out.append("")
            prev_blank = True
    return "\n".join(out).strip()


def _extract_text_from_html(body_content: bytes | str) -> str:
    try:
        from bs4 import BeautifulSoup, NavigableString, Tag
    except ImportError as exc:
        raise RuntimeError(
            "EPUB support requires the beautifulsoup4 package to be installed."
        ) from exc

    soup = BeautifulSoup(body_content, "html.parser")

    for tag in soup.find_all(_DROP_TAGS):
        tag.decompose()

    for tag in list(soup.find_all("nav")):
        epub_type = str(tag.get("epub:type", "")).lower().split()
        if _NAV_EPUB_TYPES.intersection(epub_type):
            tag.decompose()

    root = soup.body or soup
    chunks: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, NavigableString):
            text = re.sub(r"\s+", " ", str(node))
            if text.strip():
                chunks.append(text)
            return

        if not isinstance(node, Tag):
            return

        if node.name == "br":
            chunks.append("\n")
            return

        is_block = node.name in _BLOCK_TAGS
        if is_block and chunks and not chunks[-1].endswith("\n"):
            chunks.append("\n")

        for child in node.children:
            walk(child)

        if is_block:
            chunks.append("\n")

    walk(root)

    text = "".join(chunks)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return _normalize_multiline_text(text)


class EpubParser(BaseParser):
    """Parse EPUB files into plain text."""

    async def parse(self, file_content: bytes, file_name: str) -> ParseResult:
        try:
            import ebooklib
            from ebooklib import epub
        except ImportError as exc:
            raise RuntimeError(
                "EPUB support requires the EbookLib package to be installed."
            ) from exc

        book = epub.read_epub(io.BytesIO(file_content))
        items_by_id = {
            item.id: item for item in book.get_items() if getattr(item, "id", None)
        }
        text_parts: list[str] = []

        for spine_entry in book.spine:
            item_id, is_linear = self._resolve_spine_entry(spine_entry)
            if not item_id or not is_linear:
                continue

            item = items_by_id.get(item_id)
            if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue
            if hasattr(item, "is_chapter") and not item.is_chapter():
                continue

            chapter_text = _extract_text_from_html(item.get_body_content())
            if chapter_text:
                text_parts.append(chapter_text)

        if not text_parts:
            for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
                if hasattr(item, "is_chapter") and not item.is_chapter():
                    continue
                chapter_text = _extract_text_from_html(item.get_body_content())
                if chapter_text:
                    text_parts.append(chapter_text)

        return ParseResult(text="\n\n".join(text_parts).strip(), media=[])

    @staticmethod
    def _resolve_spine_entry(spine_entry: Any) -> tuple[str | None, bool]:
        if isinstance(spine_entry, tuple) and spine_entry:
            item_id = str(spine_entry[0]) if spine_entry[0] else None
            is_linear = len(spine_entry) < 2 or str(spine_entry[1]).lower() != "no"
            return item_id, is_linear
        if isinstance(spine_entry, str):
            return spine_entry, True

        item_id = getattr(spine_entry, "id", None) or getattr(
            spine_entry,
            "idref",
            None,
        )
        linear = getattr(spine_entry, "linear", "yes")
        if isinstance(item_id, str) and item_id:
            return item_id, str(linear).lower() != "no"

        return None, False
