"""Fixed-size chunking preserves text and keeps per-call options local."""

import pytest

from astrbot.core.knowledge_base.chunking.fixed_size import FixedSizeChunker


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["", "  \n\t", "abcdefghij", "中文分块测试🙂"])
async def test_nonoverlapping_chunks_preserve_every_character(text):
    chunks = await FixedSizeChunker(chunk_size=3, chunk_overlap=0).chunk(text)
    assert "".join(chunks) == text
    assert all(0 < len(chunk) <= 3 for chunk in chunks)


@pytest.mark.asyncio
async def test_call_options_do_not_mutate_chunker_defaults():
    chunker = FixedSizeChunker(chunk_size=4, chunk_overlap=1)
    assert await chunker.chunk("abcdefgh", chunk_size=2, chunk_overlap=0) == [
        "ab",
        "cd",
        "ef",
        "gh",
    ]
    assert await chunker.chunk("abcdefgh") == ["abcd", "defg", "gh"]
    assert (chunker.chunk_size, chunker.chunk_overlap) == (4, 1)
