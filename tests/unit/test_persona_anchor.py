"""Tests for astrbot.core.persona_anchor."""

from astrbot.core.persona_anchor import (
    TOOL_RESULT_CLOSE,
    TOOL_RESULT_OPEN,
    build_language_rule,
    build_persona_anchor,
    build_persona_hardening,
    detect_mixed_language,
    normalize_language,
    wrap_tool_result,
)


class TestBuildPersonaAnchor:
    def test_basic(self):
        out = build_persona_anchor("流萤")
        assert "流萤" in out
        assert out.startswith("<persona_anchor>")
        assert out.endswith("</persona_anchor>")

    def test_empty_persona_returns_empty(self):
        assert build_persona_anchor("") == ""
        assert build_persona_anchor("   ") == ""

    def test_custom_template(self):
        out = build_persona_anchor("Alice", template="Stay as {persona}!")
        assert out == "Stay as Alice!"

    def test_template_without_placeholder_is_passthrough(self):
        # A template with no placeholder at all is returned verbatim
        out = build_persona_anchor("Bob", template="no placeholder here")
        assert out == "no placeholder here"

    def test_broken_template_falls_back(self):
        # An unknown placeholder makes str.format raise -> fall back to default
        out = build_persona_anchor("Bob", template="Stay as {unknown_key}!")
        assert "Bob" in out
        assert out.startswith("<persona_anchor>")


class TestBuildPersonaHardening:
    def test_default(self):
        out = build_persona_hardening()
        assert "跳出角色" in out

    def test_with_persona(self):
        out = build_persona_hardening("流萤")
        assert "流萤" in out

    def test_custom_line(self):
        assert build_persona_hardening(line="Be yourself") == "Be yourself"

    def test_empty_line(self):
        assert build_persona_hardening(line="   ") == ""


class TestWrapToolResult:
    def test_wrap(self):
        out = wrap_tool_result('{"a": 1}')
        assert out.startswith(TOOL_RESULT_OPEN)
        assert out.endswith(TOOL_RESULT_CLOSE)
        assert '{"a": 1}' in out

    def test_empty_passthrough(self):
        assert wrap_tool_result("") == ""
        assert wrap_tool_result("   ") == "   "


class TestNormalizeLanguage:
    def test_known_codes(self):
        assert normalize_language("zh") == "中文"
        assert normalize_language("EN") == "English"
        assert normalize_language("zh-tw") == "繁體中文"
        assert normalize_language("ja") == "日本語"

    def test_unknown_passthrough(self):
        assert normalize_language("klingon") == "klingon"

    def test_empty(self):
        assert normalize_language("") == ""
        assert normalize_language("   ") == ""


class TestBuildLanguageRule:
    def test_basic(self):
        out = build_language_rule("zh")
        assert "中文" in out
        assert out.startswith("<language_rule>")
        assert out.endswith("</language_rule>")

    def test_accepts_literal_name(self):
        out = build_language_rule("中文")
        assert "中文" in out

    def test_empty_returns_empty(self):
        assert build_language_rule("") == ""
        assert build_language_rule("   ") == ""

    def test_custom_template(self):
        out = build_language_rule("en", template="Reply in {lang} only.")
        assert out == "Reply in English only."


class TestDetectMixedLanguage:
    def test_obvious_mix(self):
        assert detect_mixed_language("这是一个 good idea，我们可以 try 一下") is True

    def test_pure_chinese(self):
        assert detect_mixed_language("今天天气不错，我们去公园散步吧") is False

    def test_whitelist_proper_nouns(self):
        # GitHub / Python are whitelisted -> not a mix
        assert detect_mixed_language("请帮我看看 GitHub 上的 Python 代码") is False

    def test_whitelist_tech_terms(self):
        assert detect_mixed_language("这个 bug 出现在 Linux 环境下") is False

    def test_pure_english(self):
        assert detect_mixed_language("hello world this is english") is False

    def test_empty(self):
        assert detect_mixed_language("") is False

    def test_too_short_cjk(self):
        assert detect_mixed_language("ok 好") is False
