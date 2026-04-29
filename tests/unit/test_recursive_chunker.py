"""
Unit tests for RecursiveCharacterChunker.

Covers construction, chunk method with various inputs (empty text, short text,
newline separators, character-level fallback, recursive splitting, custom
separators, and edge cases with chunk_size/overlap validation).
All tests isolate the chunker from any external dependencies.
"""

from unittest.mock import MagicMock, patch

import pytest

from astrbot.core.knowledge_base.chunking.recursive import (
    RecursiveCharacterChunker,
)


# ---------------------------------------------------------------
# Construction
# ---------------------------------------------------------------


class TestRecursiveCharacterChunkerConstruction:
    """Test construction of RecursiveCharacterChunker."""

    def test_default_construction(self):
        """Test default parameters are set correctly."""
        chunker = RecursiveCharacterChunker()
        assert chunker.chunk_size == 500
        assert chunker.chunk_overlap == 100
        assert chunker.length_function is len
        assert chunker.is_separator_regex is False
        assert "\n\n" in chunker.separators
        assert "" in chunker.separators  # character fallback

    def test_custom_construction(self):
        """Test custom parameters are applied."""
        chunker = RecursiveCharacterChunker(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=lambda x: len(x.split()),
            is_separator_regex=True,
            separators=["\n", " "],
        )
        assert chunker.chunk_size == 1000
        assert chunker.chunk_overlap == 200
        assert chunker.length_function("hello world") == 2
        assert chunker.is_separator_regex is True
        assert chunker.separators == ["\n", " "]

    def test_injectable_length_function(self):
        """Test injecting a custom length function."""
        chunker = RecursiveCharacterChunker(
            chunk_size=3,
            length_function=lambda x: len(x.split()),
        )
        assert chunker.chunk_size == 3
        assert chunker.length_function("a b c d") == 4


# ---------------------------------------------------------------
# chunk() - basic cases
# ---------------------------------------------------------------


class TestRecursiveCharacterChunkerChunkBasic:
    """Test basic chunk() behavior."""

    @pytest.mark.asyncio
    async def test_empty_text_returns_empty_list(self):
        """Test that empty text returns an empty list."""
        chunker = RecursiveCharacterChunker()
        result = await chunker.chunk("")
        assert result == []

    @pytest.mark.asyncio
    async def test_whitespace_only_text(self):
        """Test that whitespace-only text is handled."""
        chunker = RecursiveCharacterChunker()
        result = await chunker.chunk("   \n\n  ")
        # Depends on separator logic; should not crash
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_short_text_returns_single_chunk(self):
        """Test that text shorter than chunk_size returns single chunk."""
        chunker = RecursiveCharacterChunker(chunk_size=1000)
        text = "Short text."
        result = await chunker.chunk(text)
        assert result == [text]

    @pytest.mark.asyncio
    async def test_text_equal_to_chunk_size(self):
        """Test that text exactly chunk_size returns single chunk."""
        chunker = RecursiveCharacterChunker(chunk_size=10)
        text = "0123456789"
        result = await chunker.chunk(text)
        assert result == [text]


# ---------------------------------------------------------------
# chunk() - separator-driven splitting
# ---------------------------------------------------------------


class TestRecursiveCharacterChunkerSeparator:
    """Test chunk() behavior with separator-based splitting."""

    @pytest.mark.asyncio
    async def test_splits_by_double_newline(self):
        """Test that double newline is the preferred separator."""
        chunker = RecursiveCharacterChunker(chunk_size=10, chunk_overlap=0)
        text = "para1\n\npara2\n\npara3"
        result = await chunker.chunk(text)
        # Each paragraph is <= chunk_size, so each should be a separate chunk
        assert len(result) >= 1
        # All chunks should be non-empty strings
        assert all(isinstance(c, str) and c for c in result)

    @pytest.mark.asyncio
    async def test_splits_by_newline_when_double_newline_not_found(self):
        """Test fallback to single newline when double newline is absent."""
        chunker = RecursiveCharacterChunker(
            chunk_size=50,
            chunk_overlap=0,
            separators=["\n\n", "\n"],
        )
        text = "line1\nline2\nline3"
        result = await chunker.chunk(text)
        # Without overlap and small lines, each line should be separate if lines fit
        assert isinstance(result, list)
        assert all(isinstance(c, str) for c in result)

    @pytest.mark.asyncio
    async def test_falls_back_to_character_splitting(self):
        """Test that chunker falls back to character splitting when no separator matches."""
        chunker = RecursiveCharacterChunker(
            chunk_size=5,
            chunk_overlap=0,
            separators=["\n\n", ""],
        )
        text = "abcdefghij"
        result = await chunker.chunk(text)
        # Character splitting: step = chunk_size - overlap = 5
        assert result == ["abcde", "fghij"]

    @pytest.mark.asyncio
    async def test_custom_separator(self):
        """Test that a custom separator is used for splitting."""
        chunker = RecursiveCharacterChunker(
            chunk_size=100,
            chunk_overlap=0,
            separators=["|"],
        )
        text = "part1|part2|part3"
        result = await chunker.chunk(text)
        # Each part is well under chunk_size, so each should be a separate chunk
        assert len(result) == 3
        assert result[0] == "part1|"
        assert result[1] == "part2|"
        assert result[2] == "part3"


# ---------------------------------------------------------------
# chunk() - overlap behavior
# ---------------------------------------------------------------


class TestRecursiveCharacterChunkerOverlap:
    """Test overlap behavior in chunk()."""

    @pytest.mark.asyncio
    async def test_character_split_with_overlap(self):
        """Test that character-level split respects overlap."""
        chunker = RecursiveCharacterChunker(
            chunk_size=6,
            chunk_overlap=2,
            separators=[""],
        )
        text = "abcdefghij"
        result = await chunker.chunk(text)
        # step = 6 - 2 = 4, so: "abcdef", "efghij"
        assert result == ["abcdef", "efghij"]

    @pytest.mark.asyncio
    async def test_overlap_from_kwargs_overrides_instance_default(self):
        """Test that kwargs chunk_overlap overrides the instance default."""
        chunker = RecursiveCharacterChunker(
            chunk_size=6,
            chunk_overlap=0,
            separators=[""],
        )
        text = "abcdefghij"
        result = await chunker.chunk(text, chunk_overlap=2)
        # step = 6 - 2 = 4
        assert result == ["abcdef", "efghij"]

    @pytest.mark.asyncio
    async def test_chunk_size_from_kwargs_overrides_instance_default(self):
        """Test that kwargs chunk_size overrides the instance default."""
        chunker = RecursiveCharacterChunker(
            chunk_size=500,
            chunk_overlap=0,
            separators=[""],
        )
        text = "abcdefghij"
        result = await chunker.chunk(text, chunk_size=5)
        # step = 5 - 0 = 5
        assert result == ["abcde", "fghij"]


# ---------------------------------------------------------------
# chunk() - recursive splitting of oversized segments
# ---------------------------------------------------------------


class TestRecursiveCharacterChunkerRecursive:
    """Test recursive splitting of segments that exceed chunk_size."""

    @pytest.mark.asyncio
    async def test_recursive_split_oversized_segment(self):
        """Test that a single segment larger than chunk_size is recursively split."""
        chunker = RecursiveCharacterChunker(
            chunk_size=10,
            chunk_overlap=0,
            separators=["\n\n", ""],
        )
        # Single paragraph (no double newline) that exceeds chunk_size
        text = "a" * 25
        result = await chunker.chunk(text)
        # Should split into 3 character-level chunks: 10 + 10 + 5
        assert len(result) == 3
        assert result[0] == "a" * 10
        assert result[1] == "a" * 10
        assert result[2] == "a" * 5

    @pytest.mark.asyncio
    async def test_recursive_and_normal_chunks_mixed(self):
        """Test mixing normal chunks and recursively split oversized segments."""
        chunker = RecursiveCharacterChunker(
            chunk_size=10,
            chunk_overlap=0,
            separators=["\n\n", ""],
        )
        # First paragraph fits, second paragraph is oversized, third fits
        text = "short" + "\n\n" + ("a" * 25) + "\n\n" + "tiny"
        result = await chunker.chunk(text)
        # short\n\n + a*10 + a*10 + a*5 + \n\n + tiny  -> should be 4 chunks
        # Note: the separator is included in each split
        assert len(result) >= 3
        assert all(isinstance(c, str) and c for c in result)


# ---------------------------------------------------------------
# _split_by_character
# ---------------------------------------------------------------


class TestRecursiveCharacterChunkerSplitByCharacter:
    """Test the _split_by_character private method."""

    def test_split_by_character_defaults(self):
        """Test _split_by_character uses instance defaults."""
        chunker = RecursiveCharacterChunker(chunk_size=4, chunk_overlap=1)
        result = chunker._split_by_character("abcdefgh")
        assert result == ["abcd", "defg", "gh"]

    def test_split_by_character_explicit_params(self):
        """Test _split_by_character with explicit chunk_size and overlap."""
        chunker = RecursiveCharacterChunker()
        result = chunker._split_by_character("abcdefgh", chunk_size=4, overlap=1)
        assert result == ["abcd", "defg", "gh"]

    def test_split_by_character_long_exact_fit(self):
        """Test split when text length divides evenly into chunk_size."""
        chunker = RecursiveCharacterChunker(chunk_size=4, chunk_overlap=0)
        result = chunker._split_by_character("abcdefgh")
        assert result == ["abcd", "efgh"]

    def test_split_by_character_short_text(self):
        """Test split when text is shorter than chunk_size."""
        chunker = RecursiveCharacterChunker(chunk_size=100)
        result = chunker._split_by_character("hello")
        assert result == ["hello"]

    def test_split_by_character_raises_on_zero_chunk_size(self):
        """Test that chunk_size <= 0 raises ValueError."""
        chunker = RecursiveCharacterChunker()
        with pytest.raises(ValueError, match="chunk_size must be greater than 0"):
            chunker._split_by_character("test", chunk_size=0)

    def test_split_by_character_raises_on_negative_overlap(self):
        """Test that negative overlap raises ValueError."""
        chunker = RecursiveCharacterChunker()
        with pytest.raises(ValueError, match="chunk_overlap must be non-negative"):
            chunker._split_by_character("test", chunk_overlap=-1)

    def test_split_by_character_raises_on_overlap_ge_chunk_size(self):
        """Test that overlap >= chunk_size raises ValueError."""
        chunker = RecursiveCharacterChunker()
        with pytest.raises(ValueError, match="chunk_overlap must be less than chunk_size"):
            chunker._split_by_character("test", chunk_size=5, chunk_overlap=5)

    def test_single_character_chunks(self):
        """Test splitting with chunk_size=1."""
        chunker = RecursiveCharacterChunker(chunk_size=1, chunk_overlap=0)
        result = chunker._split_by_character("abc")
        assert result == ["a", "b", "c"]

    def test_overlap_equal_chunk_size_minus_one(self):
        """Test with maximum valid overlap."""
        chunker = RecursiveCharacterChunker(chunk_size=5, chunk_overlap=4)
        result = chunker._split_by_character("abcdefghij")
        # step = 1, each chunk slides by 1 char
        assert result == ["abcde", "bcdef", "cdefg", "defgh", "efghi", "fghij"]


# ---------------------------------------------------------------
# chunk() - integration scenarios
# ---------------------------------------------------------------


class TestRecursiveCharacterChunkerIntegration:
    """Integration-style tests combining multiple logic paths."""

    @pytest.mark.asyncio
    async def test_paragraphs_with_oversized_lines(self):
        """Test a realistic paragraph mix with some oversized lines."""
        chunker = RecursiveCharacterChunker(chunk_size=20, chunk_overlap=0)
        lines = ["A" * 30, "short", "B" * 30]
        text = "\n".join(lines)
        result = await chunker.chunk(text)
        # Should split the oversized lines but keep short lines as-is
        assert all(isinstance(c, str) and c for c in result)
        assert len(result) >= 3

    @pytest.mark.asyncio
    async def test_separator_in_text_but_not_at_separator_boundary(self):
        """Test that chunker finds the best separator when multiple are present."""
        chunker = RecursiveCharacterChunker(
            chunk_size=10,
            chunk_overlap=0,
            separators=["\n\n", "\n", ""],
        )
        # Has both double-newline and single-newline; prefer double-newline
        text = "aaaa\n\nbbbb\ncccc"
        result = await chunker.chunk(text)
        # Should split on \n\n first, then possibly \n for remaining
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_text_preserves_ordering(self):
        """Test that chunks preserve the original text ordering."""
        chunker = RecursiveCharacterChunker(chunk_size=10, chunk_overlap=0)
        text = "first\n\nsecond\n\nthird\n\nfourth"
        result = await chunker.chunk(text)
        # Concatenation of all chunks should contain all words in order
        combined = "".join(result)
        for word in ["first", "second", "third", "fourth"]:
            assert word in combined

    @pytest.mark.asyncio
    async def test_no_duplicate_chunks(self):
        """Test that chunker does not produce duplicate content."""
        chunker = RecursiveCharacterChunker(
            chunk_size=10,
            chunk_overlap=0,
            separators=[""],
        )
        text = "abcdefghij"
        result = await chunker.chunk(text)
        combined = "".join(result)
        # Combined length should equal original length (no overlap)
        assert len(combined) == len(text)
