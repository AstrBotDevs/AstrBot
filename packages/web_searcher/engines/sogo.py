import random
import re
from bs4 import BeautifulSoup
from . import SearchEngine, SearchResult
from . import USER_AGENTS

from typing import List


class Sogo(SearchEngine):
    def __init__(self) -> None:
        super().__init__()
        self.base_url = "https://www.sogou.com"
        self.headers["User-Agent"] = random.choice(USER_AGENTS)

    def _set_selector(self, selector: str):
        selectors = {
            "url": "h3 > a",
            "title": "h3",
            "text": "",
            "links": "div.results > div.vrwrap:not(.middle-better-hintBox)",
            "next": "",
        }
        return selectors[selector]

    async def _get_next_page(self, query) -> str:
        url = f"{self.base_url}/web?query={query}"
        return await self._get_html(url, None)

    async def search(self, query: str, num_results: int) -> List[SearchResult]:
        results = await super().search(query, num_results)
        for result in results:
            result.url = result.url.get("href")
            if result.url.startswith("/link?"):
                result.url = self.base_url + result.url
                result.url = await self._parse_url(result.url)
        return results

    async def _parse_url(self, url) -> str:
        html = await self._get_html(url)
        soup = BeautifulSoup(html, "html.parser")
        script = soup.find("script")
        if script:
            url = re.search(r'window.location.replace\("(.+?)"\)', script.string).group(
                1
            )
        return url
