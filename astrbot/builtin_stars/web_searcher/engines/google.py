import urllib.parse
from typing import cast

from bs4 import Tag

from . import SearchEngine, SearchResult


class Google(SearchEngine):
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
        url = f"{self.base_url}/search?q={query}&hl=en&gl=us&pws=0&num=10"
        return await self._get_html(url, None)

    def _get_url(self, tag: Tag) -> str:
        href = cast(str, tag.get("href") or "")
        if href.startswith("/url?"):
            parsed = urllib.parse.urlparse(href)
            q = urllib.parse.parse_qs(parsed.query).get("q", [""])[0]
            return urllib.parse.unquote(q)
        return href

    async def search(self, query: str, num_results: int) -> list[SearchResult]:
        # Request a few extra candidates and then filter invalid Google internal links.
        rough_results = await super().search(query, max(num_results * 2, 10))
        final_results: list[SearchResult] = []
        for result in rough_results:
            if not result.url.startswith("http"):
                continue
            if "google.com/search?" in result.url:
                continue
            final_results.append(result)
            if len(final_results) >= num_results:
                break
        return final_results
