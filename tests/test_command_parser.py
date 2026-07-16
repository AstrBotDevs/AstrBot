"""Import smoke tests for astrbot.core.utils.command_parser."""

import re

from astrbot.core.utils import command_parser as command_parser_module
from astrbot.core.utils.command_parser import CommandParserMixin, CommandTokens


class TestImports:
    def test_module_importable(self):
        assert command_parser_module is not None

    def test_command_tokens_class_exists(self):
        assert CommandTokens is not None

    def test_command_parser_mixin_class_exists(self):
        assert CommandParserMixin is not None


class TestCommandTokens:
    def test_default_attributes(self):
        tokens = CommandTokens()
        assert tokens.tokens == []
        assert tokens.len == 0

    def test_get_returns_none_for_out_of_bounds(self):
        tokens = CommandTokens()
        assert tokens.get(0) is None

    def test_get_returns_stripped_token(self):
        tokens = CommandTokens()
        tokens.tokens = ["hello", "world"]
        tokens.len = 2
        assert tokens.get(0) == "hello"
        assert tokens.get(1) == "world"

    def test_get_strips_whitespace(self):
        tokens = CommandTokens()
        tokens.tokens = ["  hello  ", "world  "]
        tokens.len = 2
        assert tokens.get(0) == "hello"
        assert tokens.get(1) == "world"


class DummyParser(CommandParserMixin):
    pass


class TestCommandParserMixin:
    def setup_method(self):
        self.parser = DummyParser()

    def test_parse_commands_returns_command_tokens(self):
        result = self.parser.parse_commands("hello world")
        assert isinstance(result, CommandTokens)

    def test_parse_commands_splits_by_whitespace(self):
        result = self.parser.parse_commands("hello   world  foo")
        assert result.tokens == ["hello", "world", "foo"]
        assert result.len == 3

    def test_parse_commands_empty_string(self):
        result = self.parser.parse_commands("")
        assert result.tokens == [""]
        assert result.len == 1

    def test_regex_match_returns_true_on_match(self):
        assert self.parser.regex_match("hello world", "hello") is True

    def test_regex_match_returns_false_on_no_match(self):
        assert self.parser.regex_match("hello world", "goodbye") is False

    def test_regex_match_multiline(self):
        text = "line1\nline2\nline3"
        assert self.parser.regex_match(text, "^line2$") is True

    def test_regex_match_uses_re_search(self):
        assert self.parser.regex_match("abc123def", r"\d+") is True


class TestImportsConstValues:
    def test_re_module_available(self):
        assert re is not None
