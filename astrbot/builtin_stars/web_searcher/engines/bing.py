from . import USER_AGENT_BING, SearchEngine


class Bing(SearchEngine):
    NAME = "bing"

    def __init__(self) -> None:
        super().__init__()
        # Prefer international Bing first, keep cn endpoint as compatibility fallback.
        self.base_urls = ["https://www.bing.com", "https://cn.bing.com"]
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
