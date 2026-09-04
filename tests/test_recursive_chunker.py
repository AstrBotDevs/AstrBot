from __future__ import annotations

import pytest

from astrbot.core.knowledge_base.chunking.recursive import RecursiveCharacterChunker


def _make_split(chars: int, separator: str = "\n\n") -> str:
    return "a" * chars + separator


@pytest.mark.asyncio
async def test_overlap_never_pushes_chunks_over_chunk_size() -> None:
    # Regression test for #9901: with chunk_size=100 / overlap=30 and 80-char
    # splits, the old code built "overlap + split" chunks of 110 chars.
    chunker = RecursiveCharacterChunker(
        chunk_size=100,
        chunk_overlap=30,
        separators=["\n\n"],
    )
    text = "".join(_make_split(78) for _ in range(3))

    chunks = await chunker.chunk(text, chunk_size=100, chunk_overlap=30)

    assert chunks
    assert all(len(chunk) <= 100 for chunk in chunks), chunks
    assert all(chunk for chunk in chunks)


@pytest.mark.asyncio
async def test_small_text_returned_as_single_chunk() -> None:
    chunker = RecursiveCharacterChunker()

    assert await chunker.chunk("hello", chunk_size=100, chunk_overlap=10) == ["hello"]
    assert await chunker.chunk("", chunk_size=100, chunk_overlap=10) == []


@pytest.mark.asyncio
async def test_normal_text_chunks_within_limit() -> None:
    chunker = RecursiveCharacterChunker(
        chunk_size=50,
        chunk_overlap=10,
        separators=["\n\n"],
    )
    text = "\n\n".join(f"段落{i}" + "字" * 20 for i in range(6))

    chunks = await chunker.chunk(text, chunk_size=50, chunk_overlap=10)

    assert all(0 < len(chunk) <= 50 for chunk in chunks), chunks


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "a" * 30 + "\n\n" + "b" * 200,  # separator-driven path
        "a" * 200,  # falls through to _split_by_character
    ],
)
async def test_invalid_overlap_raises(text: str) -> None:
    chunker = RecursiveCharacterChunker()

    with pytest.raises(ValueError, match="chunk_overlap must be less than chunk_size"):
        await chunker.chunk(text, chunk_size=100, chunk_overlap=100)
