from . import SearchEngine


class Comet(SearchEngine):
    """Best-effort search via public Perplexity/Comet page.

    Note:
    - This endpoint is often protected by anti-bot challenges.
    - We intentionally treat failures as non-fatal and rely on fallback engines.
    """

    def __init__(self) -> None:
        super().__init__()
        self.base_url = "https://www.perplexity.ai"

    def _set_selector(self, selector: str):
        selectors = {
            "url": "a[href]",
            "title": "h3, h2",
            "text": "p, div",
            "links": "article, div[role='article'], li, div.result",
            "next": "",
        }
        return selectors[selector]

    async def _get_next_page(self, query: str) -> str:
        url = f"{self.base_url}/search?q={query}"
        return await self._get_html(url, None)
