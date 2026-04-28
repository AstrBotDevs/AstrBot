"""Unit tests for DifyAgentRunner._strip_think_tags"""

import pytest

from astrbot.core.agent.runners.dify.dify_agent_runner import DifyAgentRunner

strip = DifyAgentRunner._strip_think_tags


class TestStripThinkTags:
    def test_no_tags(self):
        """Normal text without any think tags should be unchanged."""
        assert strip("Hello, world!") == "Hello, world!"

    def test_single_think_block(self):
        """A complete <think>...</think> block should be removed."""
        result = strip("<think>let me reason</think>Here is my answer.")
        assert result == "Here is my answer."

    def test_think_block_with_newlines(self):
        """Multi-line think blocks should be removed."""
        text = "<think>\nStep 1: think\nStep 2: conclude\n</think>\nFinal answer."
        assert strip(text) == "Final answer."

    def test_multiple_think_blocks(self):
        """Multiple consecutive think blocks should all be removed."""
        text = "<think>block1</think>Middle<think>block2</think>End"
        assert strip(text) == "MiddleEnd"

    def test_orphan_closing_tag(self):
        """A trailing </think> without an opening tag should be removed."""
        assert strip("Some text</think>") == "Some text"

    def test_empty_think_block(self):
        """An empty <think></think> block should be removed."""
        assert strip("<think></think>Answer") == "Answer"

    def test_only_think_content(self):
        """If the entire string is a think block, result should be empty string."""
        assert strip("<think>all reasoning</think>") == ""

    def test_whitespace_trimmed(self):
        """Leading/trailing whitespace after stripping should be removed."""
        assert strip("  <think>x</think>  Answer  ") == "Answer"

    def test_no_modification_when_no_think(self):
        """Strings without think tags must be returned as-is (stripped)."""
        assert strip("  plain text  ") == "plain text"
