"""Tests for TTS text filter utility."""

import asyncio

import pytest

from astrbot.core.utils.tts_text_filter import FilteredQueue, TTSTextFilter


class TestTTSTextFilter:
    """Test TTSTextFilter.apply() with various patterns."""

    def test_builtin_markdown_bold(self):
        """Filter **bold** markdown."""
        result = TTSTextFilter.apply("Hello **world** test")
        assert result == "Hello  test"

    def test_builtin_markdown_italic(self):
        """Filter *italic* markdown."""
        result = TTSTextFilter.apply("Hello *world* test")
        assert result == "Hello  test"

    def test_builtin_parentheses(self):
        """Filter (content) in parentheses."""
        result = TTSTextFilter.apply("Hello (world) test")
        assert result == "Hello  test"

    def test_builtin_chinese_parentheses(self):
        """Filter （content） in Chinese parentheses."""
        result = TTSTextFilter.apply("Hello（world）test")
        assert result == "Hellotest"

    def test_builtin_corner_brackets(self):
        """Filter 【content】 in corner brackets."""
        result = TTSTextFilter.apply("Hello【world】test")
        assert result == "Hellotest"

    def test_builtin_square_brackets(self):
        """Filter [content] in square brackets."""
        result = TTSTextFilter.apply("Hello [world] test")
        assert result == "Hello  test"

    def test_multiple_patterns(self):
        """Filter multiple patterns in one text."""
        result = TTSTextFilter.apply(
            "**bold** and *italic* and (parens) and 【corner】"
        )
        assert result == "and  and  and"

    def test_nested_brackets_simple(self):
        """Nested brackets - only outermost is removed."""
        result = TTSTextFilter.apply("Hello (**bold**) test")
        # The inner **bold** would be filtered first, then () would catch the rest
        assert "bold" not in result

    def test_no_brackets(self):
        """Text without brackets passes through unchanged."""
        result = TTSTextFilter.apply("Hello world, this is a test.")
        assert result == "Hello world, this is a test."

    def test_empty_string(self):
        """Empty string returns empty string."""
        result = TTSTextFilter.apply("")
        assert result == ""

    def test_only_brackets(self):
        """Text with only brackets returns empty string."""
        result = TTSTextFilter.apply("(test)")
        assert result == ""

    def test_custom_rules(self):
        """Custom regex rules are applied after built-in rules."""
        # <tag> and </tag> stripped, but "world" between them remains
        result = TTSTextFilter.apply(
            "Hello <tag>world</tag> test",
            custom_rules=[r"<[^>]*>"],
        )
        assert result == "Hello world test"

    def test_invalid_custom_rule_skipped(self):
        """Invalid custom regex rules are skipped without crashing."""
        # Should not raise
        result = TTSTextFilter.apply(
            "Hello world",
            custom_rules=[r"[invalid"],  # unterminated bracket set
        )
        assert result == "Hello world"

    def test_mixed_content_with_no_match(self):
        """Content that doesn't match any pattern is preserved."""
        text = "你好，今天天气不错！"
        result = TTSTextFilter.apply(text)
        assert result == text

    def test_whitespace_trimming(self):
        """Result is stripped of leading/trailing whitespace."""
        result = TTSTextFilter.apply("  Hello world  ")
        assert result == "Hello world"


@pytest.mark.asyncio
class TestFilteredQueue:
    """Test FilteredQueue wrapper."""

    async def test_get_filtered_text(self):
        """Getting text from queue returns filtered text."""
        real_queue: asyncio.Queue = asyncio.Queue()
        fq = FilteredQueue(real_queue, custom_rules=[])

        await fq.put("Hello (world) test")
        result = await fq.get()

        assert result == "Hello  test"

    async def test_none_passthrough(self):
        """None sentinel values pass through unfiltered."""
        real_queue: asyncio.Queue = asyncio.Queue()
        fq = FilteredQueue(real_queue)

        await fq.put(None)
        result = await fq.get()

        assert result is None

    async def test_non_string_passthrough(self):
        """Non-string values pass through unfiltered."""
        real_queue: asyncio.Queue = asyncio.Queue()
        fq = FilteredQueue(real_queue)

        await fq.put(123)
        result = await fq.get()

        assert result == 123

    async def test_custom_rules_in_queue(self):
        """Custom rules are applied during get()."""
        real_queue: asyncio.Queue = asyncio.Queue()
        fq = FilteredQueue(real_queue, custom_rules=[r"<[^>]*>"])

        await fq.put("Hello <tag>world</tag>")
        result = await fq.get()

        assert result == "Hello world"

    async def test_queue_size_methods(self):
        """qsize, empty, full delegate to real queue."""
        real_queue: asyncio.Queue = asyncio.Queue(maxsize=10)
        fq = FilteredQueue(real_queue)

        assert fq.empty() is True
        assert fq.full() is False

        await fq.put("item")
        assert fq.qsize() == 1
        assert fq.empty() is False

    async def test_multiple_items(self):
        """Multiple items through the queue are all filtered."""
        real_queue: asyncio.Queue = asyncio.Queue()
        fq = FilteredQueue(real_queue)

        texts = ["Hello (world)", "Foo **bar**", "Normal text"]
        for t in texts:
            await fq.put(t)

        results = []
        for _ in texts:
            results.append(await fq.get())

        assert results[0] == "Hello"
        assert results[1] == "Foo"
        assert results[2] == "Normal text"

    async def test_filtered_with_mixed_none(self):
        """Mix of text and None pass through correctly."""
        real_queue: asyncio.Queue = asyncio.Queue()
        fq = FilteredQueue(real_queue)

        await fq.put("Hello (world)")
        await fq.put(None)
        await fq.put("**bold** text")

        assert await fq.get() == "Hello"
        assert await fq.get() is None
        assert await fq.get() == "text"
