from urllib.parse import unquote, urlencode

from . import SearchEngine


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
            "url": "a[href]",
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
