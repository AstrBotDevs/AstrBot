from __future__ import annotations

import pytest

from astrbot.core.knowledge_base.parsers.markitdown_parser import MarkitdownParser
from astrbot.core.knowledge_base.parsers.text_parser import TextParser
from astrbot.core.knowledge_base.parsers.util import select_parser


@pytest.mark.parametrize("ext", [".mdx", ".mkd"])
@pytest.mark.asyncio
async def test_markdown_variants_use_text_parser(ext: str) -> None:
    # These extensions are accepted by the MarkdownChunker whitelist in
    # kb_helper but previously had no parser route, so uploads always
    # failed with "暂时不支持的文件格式".
    parser = await select_parser(ext)

    assert isinstance(parser, TextParser)


@pytest.mark.parametrize("ext", [".html", ".htm", ".csv"])
@pytest.mark.asyncio
async def test_html_csv_use_markitdown_parser(ext: str) -> None:
    parser = await select_parser(ext)

    assert isinstance(parser, MarkitdownParser)


@pytest.mark.asyncio
async def test_markitdown_parses_html_and_csv() -> None:
    html = b"<html><body><h1>Title</h1><p>Hello <b>world</b></p></body></html>"
    result = await MarkitdownParser().parse(html, "a.html")
    assert "Title" in result.text and "Hello **world**" in result.text

    csv = b"name,age\nalice,1\n"
    result = await MarkitdownParser().parse(csv, "a.csv")
    assert "alice" in result.text


@pytest.mark.asyncio
async def test_rtf_still_unsupported() -> None:
    # markitdown-no-magika 0.1.2 has no RTF converter, so .rtf must keep
    # raising instead of being routed to a parser that cannot handle it.
    with pytest.raises(ValueError, match="暂时不支持的文件格式"):
        await select_parser(".rtf")
