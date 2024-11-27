from typing import List
from .engine import SearchEngine, SearchResult
from .config import HEADERS, USER_AGENT_BING

class Bing(SearchEngine):
    def __init__(self) -> None:
        super().__init__()
        self.base_url = "https://www.bing.com"
        self.headers.update({'User-Agent': USER_AGENT_BING})

    def _set_selector(self, selector: str):
        selectors = {
            'url': 'div.b_attribution cite', 
            'title': 'h2', 
            'text': 'p', 
            'links': 'ol#b_results > li.b_algo', 
            'next': 'div#b_content nav[role="navigation"] a.sb_pagN'
        }
        return selectors[selector]

    async def _get_next_page(self, query) -> str:
        if self.page == 1:
            await self._get_html(self.base_url)
        url = f'{self.base_url}/search?q={query}&form=QBLH&sp=-1&lq=0&pq=hi&sc=10-2&qs=n&sk=&cvid=DE75965E2D6346D681288933984DE48F&ghsh=0&ghacc=0&ghpl='
        return await self._get_html(url, None)
    
    async def search(self, query: str, num_results: int) -> List[SearchResult]:
        results = await super().search(query, num_results)
        for result in results:
            if not isinstance(result.url, str):
                result.url = result.url.text
                
        return results