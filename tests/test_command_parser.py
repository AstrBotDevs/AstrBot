"""Behavioral coverage for command tokenization and regular-expression matching."""

import pytest

from astrbot.core.utils.command_parser import CommandParserMixin, CommandTokens


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("hello world", ["hello", "world"]),
        ("a\tb\nc", ["a", "b", "c"]),
        ("", [""]),
        ("  hello  ", ["", "hello", ""]),
        ("你好 世界", ["你好", "世界"]),
    ],
)
def test_tokenization_preserves_positions(message: str, expected: list[str]) -> None:
    tokens = CommandParserMixin().parse_commands(message)
    assert tokens.tokens == expected
    assert tokens.len == len(expected)
    assert [tokens.get(i) for i in range(tokens.len)] == expected
    assert tokens.get(-1) is None
    assert tokens.get(tokens.len) is None


def test_token_lookup_strips_text_without_mutating_storage() -> None:
    tokens = CommandTokens()
    tokens.tokens = ["  first  ", "\tsecond\n"]
    tokens.len = 2
    assert tokens.get(0) == "first"
    assert tokens.get(1) == "second"
    assert tokens.tokens == ["  first  ", "\tsecond\n"]


@pytest.mark.parametrize(
    ("text", "pattern", "matches"),
    [
        ("prefix /help suffix", r"/help", True),
        ("hello\n/help", r"^/help$", True),
        ("helpful", r"^help$", False),
        ("id=42", r"\d+", True),
        ("", "", True),
    ],
)
def test_regex_search_supports_multiline_anchors(
    text: str, pattern: str, matches: bool
) -> None:
    assert CommandParserMixin().regex_match(text, pattern) is matches
