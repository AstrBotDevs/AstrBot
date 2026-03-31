import urllib.parse
from typing import cast

from bs4 import Tag

from . import SearchEngine, SearchResult


class Google(SearchEngine):
    NAME = "google"

    def __init__(self) -> None:
        super().__init__()
        self.base_url = "https://www.google.com"

    def _set_selector(self, selector: str):
        selectors = {
            "url": "a[href]",
            "title": "h3",
            "text": "div.VwiC3b, span.aCOpRe",
            "links": "div#search div.g, div#search div.MjjYud",
            "next": "a#pnnext",
        }
        return selectors[selector]

    async def _get_next_page(self, query: str) -> str:
        params = {
            "q": urllib.parse.unquote(query),
            "hl": "en",
            "gl": "us",
            "pws": "0",
            "num": "10",
        }
        url = f"{self.base_url}/search?{urllib.parse.urlencode(params)}"
        return await self._get_html(url, None)

    def _get_url(self, tag: Tag) -> str:
        href = cast(str, tag.get("href") or "")
        if href.startswith("/url?"):
            parsed = urllib.parse.urlparse(href)
            q = urllib.parse.parse_qs(parsed.query).get("q", [""])[0]
            return urllib.parse.unquote(q)
        return href

    async def search(self, query: str, num_results: int) -> list[SearchResult]:
        return await self._search_with_result_filter(
            query=query,
            num_results=num_results,
            predicate=lambda result: (
                result.url.startswith("http") and "google.com/search?" not in result.url
            ),
        )
