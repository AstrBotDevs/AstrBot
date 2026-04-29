import urllib.parse

import pytest
from bs4 import BeautifulSoup, Tag

from astrbot.builtin_stars.web_searcher.engines import SearchEngine, SearchResult
from astrbot.builtin_stars.web_searcher.engines.comet import Comet
from astrbot.builtin_stars.web_searcher.engines.duckduckgo import DuckDuckGo
from astrbot.builtin_stars.web_searcher.engines.google import Google


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


@pytest.mark.asyncio
async def test_google_get_next_page_urlencodes_query(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = Google()
    captured: dict[str, str] = {}

    async def fake_get_html(url: str, data: dict | None = None) -> str:
        captured["url"] = url
        return ""

    monkeypatch.setattr(engine, "_get_html", fake_get_html)
    await engine._get_next_page("hello%20world%2Bv2")

    parsed = urllib.parse.urlparse(captured["url"])
    params = urllib.parse.parse_qs(parsed.query)
    assert params["q"] == ["hello world+v2"]
    assert params["hl"] == ["en"]
    assert params["gl"] == ["us"]


def test_comet_get_url_prefers_href_and_supports_scheme_relative() -> None:
    engine = Comet()
    http_tag = BeautifulSoup(
        '<a href="https://example.com/result">Title</a>',
        "html.parser",
    ).find("a")
    rel_tag = BeautifulSoup('<a href="//example.org/path">Title</a>', "html.parser").find(
        "a"
    )
    assert http_tag is not None
    assert rel_tag is not None

    assert engine._get_url(http_tag) == "https://example.com/result"
    assert engine._get_url(rel_tag) == "https://example.org/path"


@pytest.mark.asyncio
async def test_comet_search_filters_internal_and_non_content_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = Comet()

    async def fake_search(
        self: SearchEngine,
        query: str,
        num_results: int,
    ) -> list[SearchResult]:
        return [
            SearchResult(title="internal", url="https://www.perplexity.ai/search?q=a", snippet=""),
            SearchResult(title="anchor", url="#section", snippet=""),
            SearchResult(title="js", url="javascript:void(0)", snippet=""),
            SearchResult(title="mailto", url="mailto:a@example.com", snippet=""),
            SearchResult(title="ok1", url="https://example.com/a", snippet=""),
            SearchResult(title="ok2", url="http://example.org/b", snippet=""),
        ]

    monkeypatch.setattr(SearchEngine, "search", fake_search)

    results = await engine.search("hello", 10)
    assert [r.url for r in results] == [
        "https://example.com/a",
        "http://example.org/b",
    ]


@pytest.mark.asyncio
async def test_search_with_result_filter_skips_fetch_on_non_positive_num_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = EngineWithoutTextSelector()
    called = {"value": False}

    async def fake_search(
        self: SearchEngine,
        query: str,
        num_results: int,
    ) -> list[SearchResult]:
        called["value"] = True
        return [SearchResult(title="t", url="https://example.com", snippet="s")]

    monkeypatch.setattr(SearchEngine, "search", fake_search)

    results_zero = await engine._search_with_result_filter(
        query="hello",
        num_results=0,
        predicate=lambda _: True,
    )
    results_negative = await engine._search_with_result_filter(
        query="hello",
        num_results=-3,
        predicate=lambda _: True,
    )

    assert results_zero == []
    assert results_negative == []
    assert called["value"] is False
