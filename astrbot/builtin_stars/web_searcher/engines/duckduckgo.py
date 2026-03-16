import urllib.parse
from typing import cast

from bs4 import Tag

from . import SearchEngine, SearchResult


class DuckDuckGo(SearchEngine):
    NAME = "duckduckgo"

    def __init__(self) -> None:
        super().__init__()
        self.base_url = "https://html.duckduckgo.com/html"

    def _set_selector(self, selector: str):
        selectors = {
            "url": "a.result__a, h2 a",
            "title": "a.result__a, h2",
            "text": "a.result__snippet, div.result__snippet",
            "links": "div.result, div.web-result",
            "next": "a.result--more__btn",
        }
        return selectors[selector]

    async def _get_next_page(self, query: str) -> str:
        params = {"q": urllib.parse.unquote(query), "kl": "us-en"}
        url = f"{self.base_url}/?{urllib.parse.urlencode(params)}"
        return await self._get_html(url, None)

    def _get_url(self, tag: Tag) -> str:
        href = cast(str, tag.get("href") or "")
        if "duckduckgo.com/l/?" in href:
            parsed = urllib.parse.urlparse(href)
            target = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
            return urllib.parse.unquote(target)
        return href

    async def search(self, query: str, num_results: int) -> list[SearchResult]:
        return await self._search_with_result_filter(
            query=query,
            num_results=num_results,
            predicate=lambda result: result.url.startswith("http"),
        )
