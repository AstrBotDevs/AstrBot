from typing import cast
from urllib.parse import unquote, urlencode, urlparse

from bs4 import Tag

from . import SearchEngine, SearchResult


class Comet(SearchEngine):
    """Best-effort search via public Perplexity/Comet page.

    Note:
    - This endpoint is often protected by anti-bot challenges.
    - We intentionally treat failures as non-fatal and rely on fallback engines.
    """
    NAME = "comet"

    def __init__(self) -> None:
        super().__init__()
        self.base_url = "https://www.perplexity.ai"

    def _set_selector(self, selector: str):
        selectors = {
            "url": "a[href^='http'], a[href^='//']",
            "title": "main h1, main h2, main h3, h3, h2",
            "text": "main article, main div[role='article'], main section, main p, p",
            "links": (
                "main article, main div[role='article'], main li, main div.result, "
                "article, div[role='article'], li, div.result"
            ),
            "next": "",
        }
        return selectors[selector]

    async def _get_next_page(self, query: str) -> str:
        url = f"{self.base_url}/search?{urlencode({'q': unquote(query)})}"
        return await self._get_html(url, None)

    def _get_url(self, tag: Tag) -> str:
        href = cast(str, tag.get("href") or "")
        if href.startswith("//"):
            return f"https:{href}"
        return href

    @staticmethod
    def _is_valid_result_url(url: str) -> bool:
        lowered = (url or "").strip().lower()
        if not lowered:
            return False
        if lowered.startswith(("#", "javascript:", "mailto:")):
            return False
        if not lowered.startswith(("http://", "https://")):
            return False

        netloc = urlparse(lowered).netloc
        if not netloc:
            return False
        if netloc.endswith("perplexity.ai"):
            return False
        return True

    async def search(self, query: str, num_results: int) -> list[SearchResult]:
        return await self._search_with_result_filter(
            query=query,
            num_results=num_results,
            predicate=lambda result: self._is_valid_result_url(result.url),
        )
