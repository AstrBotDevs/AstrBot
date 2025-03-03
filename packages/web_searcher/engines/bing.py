from typing import List
from . import SearchEngine, SearchResult
from . import USER_AGENT_BING


class Bing(SearchEngine):
    def __init__(self) -> None:
        super().__init__()
        self.base_urls = ["https://cn.bing.com", "https://www.bing.com"]
        self.headers.update({"User-Agent": USER_AGENT_BING})

    def _set_selector(self, selector: str):
        selectors = {
            "url": "div.b_attribution cite",
            "title": "h2",
            "text": "p",
            "links": "ol#b_results > li.b_algo",
            "next": 'div#b_content nav[role="navigation"] a.sb_pagN',
        }
        return selectors[selector]

    async def _get_next_page(self, query) -> str:
        # if self.page == 1:
        #     await self._get_html(self.base_url)
        for base_url in self.base_urls:
            try:
                url = f"{base_url}/search?q={query}"
                return await self._get_html(url, None)
            except Exception as _:
                self.base_url = base_url
                continue
        raise Exception("Bing search failed")

    async def search(self, query: str, num_results: int) -> List[SearchResult]:
        results = await super().search(query, num_results)
        for result in results:
            if not isinstance(result.url, str):
                result.url = result.url.text

        return results
