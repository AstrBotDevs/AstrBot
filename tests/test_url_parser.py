"""Import smoke tests for the URL parser module."""

from __future__ import annotations

from astrbot.core.knowledge_base.parsers.url_parser import (
    URLExtractor,
    extract_text_from_url,
)


class TestURLExtractorImports:
    """Verify that the main class and helper function from url_parser can be imported."""

    def test_import_url_extractor(self):
        assert URLExtractor is not None
        assert hasattr(URLExtractor, "extract_text_from_url")

    def test_import_extract_text_from_url_function(self):
        assert extract_text_from_url is not None
        assert callable(extract_text_from_url)
