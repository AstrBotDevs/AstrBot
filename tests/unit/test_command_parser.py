"""Unit tests for astrbot.core.utils.command_parser.

Covers CommandTokens data-holder and CommandParserMixin parse/regex helpers.
"""

from astrbot.core.utils.command_parser import CommandParserMixin, CommandTokens


# ---------------------------------------------------------------------------
# CommandTokens
# ---------------------------------------------------------------------------


class TestCommandTokens:
    def test_default_attributes(self):
        tokens = CommandTokens()
        assert tokens.tokens == []
        assert tokens.len == 0

    def test_get_returns_none_for_out_of_bounds_negative(self):
        tokens = CommandTokens()
        assert tokens.get(-1) is None

    def test_get_returns_none_for_out_of_bounds_positive(self):
        tokens = CommandTokens()
        tokens.tokens = ["a", "b"]
        tokens.len = 2
        assert tokens.get(2) is None
        assert tokens.get(100) is None

    def test_get_returns_stripped_token(self):
        tokens = CommandTokens()
        tokens.tokens = ["  hello  ", "world  "]
        tokens.len = 2
        assert tokens.get(0) == "hello"
        assert tokens.get(1) == "world"

    def test_get_from_empty_list(self):
        tokens = CommandTokens()
        tokens.tokens = []
        tokens.len = 0
        assert tokens.get(0) is None


# ---------------------------------------------------------------------------
# CommandParserMixin
# ---------------------------------------------------------------------------


class _ConcreteParser(CommandParserMixin):
    """Minimal concrete subclass so the mixin can be instantiated."""


class TestCommandParserMixin:
    def setup_method(self) -> None:
        self.parser = _ConcreteParser()

    def test_parse_commands_returns_command_tokens(self):
        result = self.parser.parse_commands("hello world")
        assert isinstance(result, CommandTokens)
        assert result.len == 2

    def test_parse_commands_splits_on_whitespace(self):
        result = self.parser.parse_commands("one   two\tthree\nfour")
        assert result.tokens == ["one", "two", "three", "four"]
        assert result.len == 4

    def test_parse_commands_empty_string_yields_single_empty_token(self):
        result = self.parser.parse_commands("")
        assert result.tokens == [""]
        assert result.len == 1

    def test_parse_commands_only_whitespace(self):
        result = self.parser.parse_commands("   \t  \n  ")
        assert result.tokens == ["", ""]  # \S+ splits on whitespace runs
        # Actually re.split(r"\s+", "   \t  \n  ") = ['', '']

    def test_regex_match_returns_true_on_match(self):
        assert self.parser.regex_match("hello world", "hello") is True

    def test_regex_match_returns_false_on_no_match(self):
        assert self.parser.regex_match("hello world", "goodbye") is False

    def test_regex_match_multiline(self):
        text = "line1\nline2\nline3"
        assert self.parser.regex_match(text, "^line2$") is True

    def test_regex_match_with_digits(self):
        assert self.parser.regex_match("abc123def", r"\d+") is True

    def test_regex_match_with_special_regex_chars(self):
        """Special regex characters should be treated as regex, not literal."""
        assert self.parser.regex_match("price is 10.50", r"\d+\.\d+") is True

    def test_regex_match_empty_pattern(self):
        """An empty pattern matches any string (re.search always finds '')."""
        assert self.parser.regex_match("anything", "") is True
