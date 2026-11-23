"""The built-in searcher formats results and tries engines without network access."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.builtin_stars.web_searcher.engines import SearchResult
from astrbot.builtin_stars.web_searcher.main import Main
from astrbot.builtin_stars.web_searcher.provider_routing import DEFAULT_ENGINE_ORDER


@pytest.mark.asyncio
@pytest.mark.parametrize("include_link", [True, False])
async def test_search_result_contains_bounded_page_excerpt(monkeypatch, include_link):
    searcher = Main.__new__(Main)
    fetch = AsyncMock(return_value="x" * 800)
    monkeypatch.setattr(searcher, "_get_from_url", fetch)
    result = SearchResult(
        title="Example", url="https://example.invalid", snippet="Summary"
    )
    output = await searcher._process_search_result(result, 2, include_link)
    header = "2. Example " + (result.url if include_link else "")
    assert output == header + "\nSummary\n" + "x" * 700 + "...\n\n"
    fetch.assert_awaited_once_with(result.url)


@pytest.mark.asyncio
async def test_failed_page_fetch_retains_title_and_snippet(monkeypatch):
    searcher = Main.__new__(Main)
    monkeypatch.setattr(
        searcher, "_get_from_url", AsyncMock(side_effect=OSError("offline"))
    )
    result = SearchResult(
        title="Example", url="https://example.invalid", snippet="Summary"
    )
    assert (
        await searcher._process_search_result(result, 1, False)
        == "1. Example \nSummary\n\n\n"
    )


@pytest.mark.asyncio
async def test_engine_fallback_stops_at_first_nonempty_result():
    searcher = Main.__new__(Main)
    wanted = [
        SearchResult(title="Result", url="https://example.invalid", snippet="Found")
    ]
    engines = {
        name: SimpleNamespace(search=AsyncMock(return_value=[]))
        for name in DEFAULT_ENGINE_ORDER
    }
    engines[DEFAULT_ENGINE_ORDER[0]].search.side_effect = OSError("offline")
    engines[DEFAULT_ENGINE_ORDER[2]].search.return_value = wanted
    searcher.default_search_engines = engines
    assert await searcher._web_search_default("query", 3) is wanted
    for index, name in enumerate(DEFAULT_ENGINE_ORDER):
        if index <= 2:
            engines[name].search.assert_awaited_once_with("query", 3)
        else:
            engines[name].search.assert_not_awaited()


def test_legacy_key_migration_saves_configuration_and_preserves_lists():
    class Config(dict):
        save_config = Mock()

    config = Config(
        provider_settings={
            "websearch_tavily_key": "one",
            "websearch_bocha_key": ["two"],
        }
    )
    searcher = Main(SimpleNamespace(get_config=lambda: config))
    assert config["provider_settings"] == {
        "websearch_tavily_key": ["one"],
        "websearch_bocha_key": ["two"],
    }
    config.save_config.assert_called_once_with()
    assert set(searcher.default_search_engines) == set(DEFAULT_ENGINE_ORDER)
