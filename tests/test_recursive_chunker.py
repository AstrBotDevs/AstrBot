"""Recursive splitting preserves separators, ordering, and call isolation."""

import pytest

from astrbot.core.knowledge_base.chunking.recursive import RecursiveCharacterChunker


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    ["", "alpha\n\nbeta\n\ngamma", "unbrokencharacters", "甲乙丙\n丁戊己", "  \n\t  "],
)
async def test_nonoverlapping_chunks_preserve_source_order(text):
    chunks = await RecursiveCharacterChunker(chunk_size=6, chunk_overlap=0).chunk(text)
    assert "".join(chunks) == text
    assert all(0 < len(chunk) <= 6 for chunk in chunks)


@pytest.mark.asyncio
async def test_overrides_leave_instance_configuration_unchanged():
    chunker = RecursiveCharacterChunker(chunk_size=4, chunk_overlap=1, separators=[""])
    assert await chunker.chunk("abcdefgh", chunk_size=3, chunk_overlap=0) == [
        "abc",
        "def",
        "gh",
    ]
    assert await chunker.chunk("abcdefgh") == ["abcd", "defg", "gh"]
    assert (chunker.chunk_size, chunker.chunk_overlap) == (4, 1)
