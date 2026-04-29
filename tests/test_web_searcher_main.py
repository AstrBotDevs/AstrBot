from __future__ import annotations

from astrbot.api.star import Star
from astrbot.builtin_stars.web_searcher.main import Main


def test_web_searcher_main_imported():
    assert Main is not None


def test_web_searcher_main_class():
    assert issubclass(Main, Star)


def test_web_searcher_main_tools():
    assert hasattr(Main, "TOOLS")
    assert "web_search" in Main.TOOLS
    assert "fetch_url" in Main.TOOLS
    assert "web_search_tavily" in Main.TOOLS
