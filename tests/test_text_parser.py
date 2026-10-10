from __future__ import annotations

import codecs

import pytest

from astrbot.core.knowledge_base.parsers.text_parser import TextParser


@pytest.mark.asyncio
async def test_parse_utf8() -> None:
    parser = TextParser()

    result = await parser.parse("你好, world".encode(), "a.txt")

    assert result.text == "你好, world"
    assert result.media == []


@pytest.mark.asyncio
async def test_parse_utf8_with_bom() -> None:
    parser = TextParser()

    result = await parser.parse(
        codecs.BOM_UTF8 + "带 BOM 的内容".encode(),
        "a.txt",
    )

    assert result.text == "带 BOM 的内容"


@pytest.mark.asyncio
async def test_parse_utf16_le_with_bom() -> None:
    # Windows Notepad "Unicode" (UTF-16 LE with BOM) saved txt files.
    parser = TextParser()

    result = await parser.parse(
        codecs.BOM_UTF16_LE + "Windows 记事本 Unicode".encode("utf-16-le"),
        "a.txt",
    )

    assert result.text == "Windows 记事本 Unicode"


@pytest.mark.asyncio
async def test_parse_utf16_be_with_bom() -> None:
    parser = TextParser()

    result = await parser.parse(
        codecs.BOM_UTF16_BE + "big endian".encode("utf-16-be"),
        "a.txt",
    )

    assert result.text == "big endian"


@pytest.mark.asyncio
async def test_parse_gbk() -> None:
    parser = TextParser()

    result = await parser.parse("中文内容".encode("gbk"), "a.txt")

    assert result.text == "中文内容"


@pytest.mark.asyncio
async def test_parse_undecodable_raises_value_error() -> None:
    parser = TextParser()

    with pytest.raises(ValueError, match="无法解码文件"):
        await parser.parse(b"\x81\x7f\x81\x7f\xff", "a.txt")
