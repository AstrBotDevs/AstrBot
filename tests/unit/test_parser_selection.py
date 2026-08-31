import pytest

from astrbot.core.knowledge_base.parsers.markitdown_parser import MarkitdownParser
from astrbot.core.knowledge_base.parsers.text_parser import TextParser
from astrbot.core.knowledge_base.parsers.util import select_parser


@pytest.mark.asyncio
async def test_plain_text_formats_use_text_parser():
    for ext in (".txt", ".md", ".markdown"):
        parser = await select_parser(ext)
        assert isinstance(parser, TextParser)


@pytest.mark.asyncio
async def test_rich_text_formats_use_markitdown_parser():
    for ext in (".rst", ".adoc", ".xlsx", ".docx", ".xls"):
        parser = await select_parser(ext)
        assert isinstance(parser, MarkitdownParser)


@pytest.mark.asyncio
async def test_unsupported_format_raises():
    with pytest.raises(ValueError, match="不支持"):
        await select_parser(".exe")
