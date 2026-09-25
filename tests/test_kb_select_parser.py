from __future__ import annotations

import sys

import pytest

from astrbot.core.exceptions import KnowledgeBaseUploadError
from astrbot.core.knowledge_base.parsers.markitdown_parser import MarkitdownParser
from astrbot.core.knowledge_base.parsers.text_parser import TextParser
from astrbot.core.knowledge_base.parsers.util import select_parser


@pytest.mark.parametrize("ext", [".txt", ".md", ".markdown"])
@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_text_formats_use_text_parser(ext: str) -> None:
    parser = await select_parser(ext)

    assert isinstance(parser, TextParser)


@pytest.mark.parametrize("ext", [".rst", ".adoc", ".xlsx", ".docx", ".xls"])
@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_office_formats_use_markitdown_parser(ext: str) -> None:
    parser = await select_parser(ext)

    assert isinstance(parser, MarkitdownParser)


@pytest.mark.asyncio
async def test_epub_and_pdf_routing() -> None:
    from astrbot.core.knowledge_base.parsers.epub_parser import EpubParser
    from astrbot.core.knowledge_base.parsers.pdf_parser import PDFParser

    assert isinstance(await select_parser(".epub"), EpubParser)
    assert isinstance(await select_parser(".pdf"), PDFParser)


@pytest.mark.asyncio
async def test_unsupported_ext_raises() -> None:
    with pytest.raises(ValueError, match="暂时不支持的文件格式"):
        await select_parser(".exe")


@pytest.mark.asyncio
async def test_missing_markitdown_dependency_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Drop cached modules so the lazy import runs again, then make
    # `import markitdown_no_magika` fail as if the package were absent.
    for name in list(sys.modules):
        if name == "markitdown_no_magika" or name.endswith("markitdown_parser"):
            monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "markitdown_no_magika", None)

    with pytest.raises(KnowledgeBaseUploadError, match="markitdown-no-magika"):
        await select_parser(".docx")
