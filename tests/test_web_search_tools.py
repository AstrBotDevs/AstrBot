"""Import smoke tests for web_search_tools module."""

import pytest


class TestWebSearchToolsImports:
    """Verify web_search_tools.py module can be imported and key classes exist."""

    def test_module_import(self):
        """Import the module without error."""
        from astrbot.core.tools import web_search_tools
        assert web_search_tools is not None

    def test_search_result_class(self):
        """SearchResult dataclass is present."""
        from astrbot.core.tools.web_search_tools import SearchResult
        assert SearchResult is not None

    def test_tavily_web_search_tool(self):
        """TavilyWebSearchTool is present."""
        from astrbot.core.tools.web_search_tools import TavilyWebSearchTool
        assert TavilyWebSearchTool is not None
        assert TavilyWebSearchTool.name == "web_search_tavily"

    def test_tavily_extract_web_page_tool(self):
        """TavilyExtractWebPageTool is present."""
        from astrbot.core.tools.web_search_tools import TavilyExtractWebPageTool
        assert TavilyExtractWebPageTool is not None
        assert TavilyExtractWebPageTool.name == "tavily_extract_web_page"

    def test_bocha_web_search_tool(self):
        """BochaWebSearchTool is present."""
        from astrbot.core.tools.web_search_tools import BochaWebSearchTool
        assert BochaWebSearchTool is not None
        assert BochaWebSearchTool.name == "web_search_bocha"

    def test_brave_web_search_tool(self):
        """BraveWebSearchTool is present."""
        from astrbot.core.tools.web_search_tools import BraveWebSearchTool
        assert BraveWebSearchTool is not None
        assert BraveWebSearchTool.name == "web_search_brave"

    def test_firecrawl_web_search_tool(self):
        """FirecrawlWebSearchTool is present."""
        from astrbot.core.tools.web_search_tools import FirecrawlWebSearchTool
        assert FirecrawlWebSearchTool is not None
        assert FirecrawlWebSearchTool.name == "web_search_firecrawl"

    def test_firecrawl_extract_web_page_tool(self):
        """FirecrawlExtractWebPageTool is present."""
        from astrbot.core.tools.web_search_tools import FirecrawlExtractWebPageTool
        assert FirecrawlExtractWebPageTool is not None
        assert FirecrawlExtractWebPageTool.name == "firecrawl_extract_web_page"

    def test_baidu_web_search_tool(self):
        """BaiduWebSearchTool is present."""
        from astrbot.core.tools.web_search_tools import BaiduWebSearchTool
        assert BaiduWebSearchTool is not None
        assert BaiduWebSearchTool.name == "web_search_baidu"

    def test_constant_names(self):
        """WEB_SEARCH_TOOL_NAMES constant is present."""
        from astrbot.core.tools.web_search_tools import WEB_SEARCH_TOOL_NAMES
        assert isinstance(WEB_SEARCH_TOOL_NAMES, list)
        assert len(WEB_SEARCH_TOOL_NAMES) > 0

    def test_normalize_function(self):
        """normalize_legacy_web_search_config is importable."""
        from astrbot.core.tools.web_search_tools import normalize_legacy_web_search_config
        assert callable(normalize_legacy_web_search_config)
