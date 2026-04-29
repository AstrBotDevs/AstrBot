"""
Unit tests for FixedSizeChunker.

Covers construction, chunk method with various inputs (empty text, short text,
exact fit, overlap behavior, edge cases with chunk_size/overlap parameters,
and kwargs overriding instance defaults).
All tests isolate the chunker from any external dependencies.
"""

import pytest

from astrbot.core.knowledge_base.chunking.fixed_size import FixedSizeChunker


# ---------------------------------------------------------------
# Construction
# ---------------------------------------------------------------


class TestFixedSizeChunkerConstruction:
    """Test construction of FixedSizeChunker."""

    def test_default_construction(self):
        """Test default parameters are set correctly."""
        chunker = FixedSizeChunker()
        assert chunker.chunk_size == 512
        assert chunker.chunk_overlap == 50

    def test_custom_construction(self):
        """Test custom parameters are applied."""
        chunker = FixedSizeChunker(chunk_size=256, chunk_overlap=32)
        assert chunker.chunk_size == 256
        assert chunker.chunk_overlap == 32

    def test_zero_overlap_construction(self):
        """Test that overlap of 0 is accepted."""
        chunker = FixedSizeChunker(chunk_size=100, chunk_overlap=0)
        assert chunker.chunk_size == 100
        assert chunker.chunk_overlap == 0

    def test_large_overlap_construction(self):
        """Test that overlap >= chunk_size is accepted at construction."""
        chunker = FixedSizeChunker(chunk_size=10, chunk_overlap=10)
        assert chunker.chunk_size == 10
        assert chunker.chunk_overlap == 10


# ---------------------------------------------------------------
# chunk() - basic cases
# ---------------------------------------------------------------


class TestFixedSizeChunkerChunkBasic:
    """Test basic chunk() behavior."""

    @pytest.mark.asyncio
    async def test_empty_text_returns_empty_list(self):
        """Test that empty text returns an empty list."""
        chunker = FixedSizeChunker()
        result = await chunker.chunk("")
        assert result == []

    @pytest.mark.asyncio
    async def test_short_text_returns_single_chunk(self):
        """Test that text shorter than chunk_size returns a single chunk."""
        chunker = FixedSizeChunker(chunk_size=100)
        text = "Short text."
        result = await chunker.chunk(text)
        assert result == [text]

    @pytest.mark.asyncio
    async def test_exact_fit_returns_single_chunk(self):
        """Test that text exactly chunk_size returns a single chunk."""
        chunker = FixedSizeChunker(chunk_size=10)
        text = "0123456789"
        result = await chunker.chunk(text)
        assert result == [text]

    @pytest.mark.asyncio
    async def test_text_longer_than_chunk_size(self):
        """Test that text longer than chunk_size is split into multiple chunks."""
        chunker = FixedSizeChunker(chunk_size=5, chunk_overlap=0)
        text = "abcdefghij"
        result = await chunker.chunk(text)
        assert result == ["abcde", "fghij"]

    @pytest.mark.asyncio
    async def test_whitespace_only_text(self):
        """Test that whitespace-only text is handled without crashing."""
        chunker = FixedSizeChunker()
        result = await chunker.chunk("   \n\n  ")
        assert isinstance(result, list)


# ---------------------------------------------------------------
# chunk() - overlap behavior
# ---------------------------------------------------------------


class TestFixedSizeChunkerOverlap:
    """Test overlap behavior in chunk()."""

    @pytest.mark.asyncio
    async def test_overlap_between_chunks(self):
        """Test that chunks overlap correctly."""
        chunker = FixedSizeChunker(chunk_size=6, chunk_overlap=2)
        text = "abcdefghij"
        result = await chunker.chunk(text)
        # start=0: "abcdef", start=4: "efghij"
        assert result == ["abcdef", "efghij"]

    @pytest.mark.asyncio
    async def test_overlap_equal_to_chunk_size(self):
        """Test that when overlap >= chunk_size, the algorithm prevents an infinite loop."""
        chunker = FixedSizeChunker(chunk_size=5, chunk_overlap=5)
        text = "abcdefghij"
        result = await chunker.chunk(text)
        # start=0: "abcde", since start >= end (5 >= 5), start becomes end
        # no infinite loop; next: start=5: "fghij"
        assert result == ["abcde", "fghij"]

    @pytest.mark.asyncio
    async def test_overlap_greater_than_chunk_size(self):
        """Test that when overlap > chunk_size, the algorithm prevents an infinite loop."""
        chunker = FixedSizeChunker(chunk_size=5, chunk_overlap=10)
        text = "abcdefghij"
        result = await chunker.chunk(text)
        # start=0: "abcde", since start >= end (10 >= 5), start becomes end
        # start=5: "fghij"
        assert result == ["abcde", "fghij"]

    @pytest.mark.asyncio
    async def test_no_overlap(self):
        """Test that zero overlap produces non-overlapping chunks."""
        chunker = FixedSizeChunker(chunk_size=5, chunk_overlap=0)
        text = "abcdefghij"
        result = await chunker.chunk(text)
        assert result == ["abcde", "fghij"]

    @pytest.mark.asyncio
    async def test_partial_last_chunk_with_overlap(self):
        """Test the last chunk is included even when shorter than chunk_size."""
        chunker = FixedSizeChunker(chunk_size=6, chunk_overlap=2)
        text = "abcdefgh"
        result = await chunker.chunk(text)
        # start=0: "abcdef", start=4: "efgh"
        assert result == ["abcdef", "efgh"]


# ---------------------------------------------------------------
# chunk() - kwargs override instance defaults
# ---------------------------------------------------------------


class TestFixedSizeChunkerKwargs:
    """Test that kwargs override instance defaults in chunk()."""

    @pytest.mark.asyncio
    async def test_chunk_size_kwarg_overrides_instance(self):
        """Test that chunk_size in kwargs overrides the instance default."""
        chunker = FixedSizeChunker(chunk_size=500, chunk_overlap=0)
        text = "abcdefghij"
        result = await chunker.chunk(text, chunk_size=5)
        assert result == ["abcde", "fghij"]

    @pytest.mark.asyncio
    async def test_chunk_overlap_kwarg_overrides_instance(self):
        """Test that chunk_overlap in kwargs overrides the instance default."""
        chunker = FixedSizeChunker(chunk_size=6, chunk_overlap=0)
        text = "abcdefghij"
        result = await chunker.chunk(text, chunk_overlap=2)
        assert result == ["abcdef", "efghij"]

    @pytest.mark.asyncio
    async def test_both_kwargs_override(self):
        """Test that both kwargs override instance defaults."""
        chunker = FixedSizeChunker(chunk_size=100, chunk_overlap=10)
        text = "abcdefghijklmnopqrstuvwxyz"
        result = await chunker.chunk(text, chunk_size=10, chunk_overlap=3)
        # start=0: "abcdefghij", start=7: "hijklmnopq", start=14: "opqrstuvwx",
        # start=21: "vwxyz"
        assert len(result) == 4


# ---------------------------------------------------------------
# chunk() - edge cases
# ---------------------------------------------------------------


class TestFixedSizeChunkerEdgeCases:
    """Test edge cases for chunk()."""

    @pytest.mark.asyncio
    async def test_single_character_chunks(self):
        """Test with chunk_size=1."""
        chunker = FixedSizeChunker(chunk_size=1, chunk_overlap=0)
        text = "abc"
        result = await chunker.chunk(text)
        assert result == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_chunk_size_one_with_overlap(self):
        """Test with chunk_size=1 and overlap=1 (should not infinite loop)."""
        chunker = FixedSizeChunker(chunk_size=1, chunk_overlap=1)
        text = "abc"
        result = await chunker.chunk(text)
        # start=0: "a", start>=end (1>=1) -> start=1, "b", ...
        assert result == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_large_text(self):
        """Test with a large chunk size that covers the entire text."""
        chunker = FixedSizeChunker(chunk_size=1000, chunk_overlap=50)
        text = "A" * 900
        result = await chunker.chunk(text)
        assert result == [text]

    @pytest.mark.asyncio
    async def test_text_with_newlines(self):
        """Test that newlines are handled as regular characters."""
        chunker = FixedSizeChunker(chunk_size=10, chunk_overlap=5)
        text = "line1\nline2\nline3"
        result = await chunker.chunk(text)
        assert isinstance(result, list)
        assert all(isinstance(c, str) for c in result)
        # All characters should be accounted for
        assert sum(len(c) for c in result) >= len(text)

    @pytest.mark.asyncio
    async def test_unicode_text(self):
        """Test that unicode characters are handled correctly."""
        chunker = FixedSizeChunker(chunk_size=5, chunk_overlap=2)
        text = "你好世界abc"
        result = await chunker.chunk(text)
        # Chinese characters are 1 char each in Python
        assert isinstance(result, list)
        assert "".join(result) == text

    @pytest.mark.asyncio
    async def test_exact_multiple_of_chunk_size(self):
        """Test when text length is an exact multiple of chunk_size (no overlap)."""
        chunker = FixedSizeChunker(chunk_size=5, chunk_overlap=0)
        text = "abcde" * 3  # 15 chars
        result = await chunker.chunk(text)
        assert result == ["abcde", "fghij", "klmno"]

    @pytest.mark.asyncio
    async def test_overlap_larger_than_chunk_minus_one(self):
        """Test with overlap = chunk_size - 1 (maximum information overlap)."""
        chunker = FixedSizeChunker(chunk_size=5, chunk_overlap=4)
        text = "abcdefghij"
        result = await chunker.chunk(text)
        # start=0: "abcde", start=1: "bcdef", ..., start=5: "fghij"
        assert result == ["abcde", "bcdef", "cdefg", "defgh", "efghi", "fghij"]

    @pytest.mark.asyncio
    async def test_ten_thousand_characters(self):
        """Test that chunker handles a moderately long string without issue."""
        chunker = FixedSizeChunker(chunk_size=100, chunk_overlap=10)
        text = "x" * 10000
        result = await chunker.chunk(text)
        # Expected length: ceil((10000 - 10) / (100 - 10)) = ceil(9990/90) = 111
        assert len(result) == 111
        assert all(len(c) == 100 or len(c) == 100 for c in result[:-1])
        assert len(result[-1]) <= 100


# ---------------------------------------------------------------
# chunk() - verification of no content loss
# ---------------------------------------------------------------


class TestFixedSizeChunkerContentPreservation:
    """Test that chunk() does not lose or reorder content."""

    @pytest.mark.asyncio
    async def test_no_content_loss_without_overlap(self):
        """Test no content loss when overlap is 0."""
        chunker = FixedSizeChunker(chunk_size=10, chunk_overlap=0)
        text = "0123456789" * 5  # 50 chars
        result = await chunker.chunk(text)
        combined = "".join(result)
        assert combined == text

    @pytest.mark.asyncio
    async def test_no_content_loss_with_overlap(self):
        """Test that with overlap, original content is fully represented."""
        chunker = FixedSizeChunker(chunk_size=10, chunk_overlap=3)
        text = "0123456789" * 5
        result = await chunker.chunk(text)
        # With overlap, combined will be longer than original
        combined = "".join(result)
        assert len(combined) >= len(text)
        for i, char in enumerate(text):
            assert char in combined

    @pytest.mark.asyncio
    async def test_chunks_are_substrings(self):
        """Test that all chunks are valid substrings of the original text."""
        chunker = FixedSizeChunker(chunk_size=7, chunk_overlap=3)
        text = "abcdefghijklmnop"
        result = await chunker.chunk(text)
        for chunk in result:
            assert chunk in text

    @pytest.mark.asyncio
    async def test_chunks_preserve_order(self):
        """Test that chunks appear in the same order as the original text."""
        chunker = FixedSizeChunker(chunk_size=5, chunk_overlap=2)
        text = "abcdefghij"
        result = await chunker.chunk(text)
        # Every chunk should be a substring and order should be consistent
        positions = [text.index(chunk) for chunk in result]
        assert positions == sorted(positions)
