"""Tests for astrbot.core.star.plugin_categories module."""

import pytest

from astrbot.core.star import plugin_categories
from astrbot.core.star.plugin_categories import (
    DEFAULT_PLUGIN_CATEGORY,
    PLUGIN_CATEGORY_SLUGS,
    normalize_plugin_category,
)


class TestNormalizePluginCategory:
    """Test cases for normalize_plugin_category."""

    @pytest.mark.parametrize("slug", PLUGIN_CATEGORY_SLUGS)
    def test_accepts_supported_slug(self, slug: str):
        """Every supported slug is returned unchanged."""
        assert normalize_plugin_category(slug) == slug

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("  ai_tools  ", "ai_tools"),
            ("AI_TOOLS", "ai_tools"),
            ("AI Tools", "ai_tools"),
            ("ai-tools", "ai_tools"),
            ("Long-term Memory", "long_term_memory"),
        ],
    )
    def test_normalizes_slug_spelling(self, raw: str, expected: str):
        """Case, whitespace and separators do not change the resulting slug."""
        assert normalize_plugin_category(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "   "])
    def test_missing_category_stays_undeclared(self, raw):
        """An absent category is reported as None instead of the fallback."""
        assert normalize_plugin_category(raw) is None

    @pytest.mark.parametrize(
        "raw",
        ["not_a_category", "工具", 1, ["ai_tools"], {"name": "ai_tools"}],
    )
    def test_unsupported_category_falls_back(self, raw):
        """Unsupported values degrade to the fallback category."""
        assert normalize_plugin_category(raw) == DEFAULT_PLUGIN_CATEGORY

    def test_unsupported_category_warns(self, monkeypatch: pytest.MonkeyPatch):
        """Degrading an unsupported value is reported in the log."""
        warnings: list[str] = []
        monkeypatch.setattr(
            plugin_categories.logger,
            "warning",
            lambda message: warnings.append(message),
        )

        assert normalize_plugin_category("Not A Category") == DEFAULT_PLUGIN_CATEGORY
        assert len(warnings) == 1
        assert "Not A Category" in warnings[0]

    def test_unsupported_category_can_skip_the_warning(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Callers that already validated the metadata can suppress the report."""
        warnings: list[str] = []
        monkeypatch.setattr(
            plugin_categories.logger,
            "warning",
            lambda message: warnings.append(message),
        )

        assert (
            normalize_plugin_category("Not A Category", warn=False)
            == DEFAULT_PLUGIN_CATEGORY
        )
        assert warnings == []

    def test_supported_category_does_not_warn(self, monkeypatch: pytest.MonkeyPatch):
        """A supported category is accepted silently."""
        warnings: list[str] = []
        monkeypatch.setattr(
            plugin_categories.logger,
            "warning",
            lambda message: warnings.append(message),
        )

        assert normalize_plugin_category("tools") == "tools"
        assert warnings == []
