import urllib.parse
from typing import cast

from bs4 import Tag

from . import SearchEngine, SearchResult


class DuckDuckGo(SearchEngine):
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
        url = f"{self.base_url}/?q={query}&kl=us-en"
        return await self._get_html(url, None)

    def _get_url(self, tag: Tag) -> str:
        href = cast(str, tag.get("href") or "")
        if "duckduckgo.com/l/?" in href:
            parsed = urllib.parse.urlparse(href)
            target = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
            return urllib.parse.unquote(target)
        return href

    async def search(self, query: str, num_results: int) -> list[SearchResult]:
        rough_results = await super().search(query, max(num_results * 2, 10))
        final_results: list[SearchResult] = []
        for result in rough_results:
            if not result.url.startswith("http"):
                continue
            final_results.append(result)
            if len(final_results) >= num_results:
                break
        return final_results
