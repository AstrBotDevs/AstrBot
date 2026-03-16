import urllib.parse

import pytest
from bs4 import Tag

from astrbot.builtin_stars.web_searcher.engines import SearchEngine
from astrbot.builtin_stars.web_searcher.engines.comet import Comet
from astrbot.builtin_stars.web_searcher.engines.duckduckgo import DuckDuckGo


class EngineWithoutTextSelector(SearchEngine):
    def _set_selector(self, selector: str) -> str:
        selectors = {
            "url": "a.title",
            "title": "a.title",
            "links": "div.item",
            "next": "",
        }
        return selectors[selector]

    async def _get_next_page(self, query: str) -> str:
        return """
        <div class="item">
            <a class="title" href="https://example.com/a">Example Title</a>
        </div>
        """

    def _get_url(self, tag: Tag) -> str:
        return str(tag.get("href") or "")


@pytest.mark.asyncio
async def test_base_search_allows_engine_without_text_selector() -> None:
    engine = EngineWithoutTextSelector()
    results = await engine.search("hello world", 3)

    assert len(results) == 1
    assert results[0].title == "Example Title"
    assert results[0].url == "https://example.com/a"
    assert results[0].snippet == ""


@pytest.mark.asyncio
async def test_duckduckgo_get_next_page_urlencodes_query(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = DuckDuckGo()
    captured: dict[str, str] = {}

    async def fake_get_html(url: str, data: dict | None = None) -> str:
        captured["url"] = url
        return ""

    monkeypatch.setattr(engine, "_get_html", fake_get_html)
    await engine._get_next_page("hello%20world%2Bv2")

    parsed = urllib.parse.urlparse(captured["url"])
    params = urllib.parse.parse_qs(parsed.query)
    assert params["q"] == ["hello world+v2"]
    assert params["kl"] == ["us-en"]


@pytest.mark.asyncio
async def test_comet_get_next_page_urlencodes_query(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = Comet()
    captured: dict[str, str] = {}

    async def fake_get_html(url: str, data: dict | None = None) -> str:
        captured["url"] = url
        return ""

    monkeypatch.setattr(engine, "_get_html", fake_get_html)
    await engine._get_next_page("astrbot%20rtk%20scrapling%2Btest")

    parsed = urllib.parse.urlparse(captured["url"])
    params = urllib.parse.parse_qs(parsed.query)
    assert params["q"] == ["astrbot rtk scrapling+test"]
