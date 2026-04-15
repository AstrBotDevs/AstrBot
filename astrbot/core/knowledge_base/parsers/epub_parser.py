"""EPUB document parser."""

from __future__ import annotations

import io
import re
from typing import Any

from astrbot.core.knowledge_base.parsers.base import BaseParser, ParseResult

_DROP_TAGS = ("script", "style", "nav")


def _normalize_multiline_text(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _extract_text_from_html(body_content: bytes | str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(body_content, "html.parser")
    for tag_name in _DROP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    root = soup.body or soup
    return _normalize_multiline_text(root.get_text("\n", strip=True))


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
        text_parts: list[str] = []

        for spine_entry in book.spine:
            item_id = self._resolve_spine_item_id(spine_entry)
            if not item_id:
                continue

            item = book.get_item_with_id(item_id)
            if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue
            if "nav" in getattr(item, "properties", []):
                continue

            chapter_text = _extract_text_from_html(item.get_body_content())
            if chapter_text:
                text_parts.append(chapter_text)

        return ParseResult(text="\n\n".join(text_parts).strip(), media=[])

    @staticmethod
    def _resolve_spine_item_id(spine_entry: Any) -> str | None:
        if isinstance(spine_entry, tuple) and spine_entry:
            return str(spine_entry[0])
        if isinstance(spine_entry, str):
            return spine_entry

        item_id = getattr(spine_entry, "id", None)
        if isinstance(item_id, str) and item_id:
            return item_id

        item_ref = getattr(spine_entry, "idref", None)
        if isinstance(item_ref, str) and item_ref:
            return item_ref

        return None
