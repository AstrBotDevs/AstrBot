import random
import re
from typing import cast

from bs4 import BeautifulSoup, Tag

from . import USER_AGENTS, SearchEngine, SearchResult


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

    def _get_url(self, tag: Tag) -> str:
        return cast(str, tag.get("href"))

    async def search(self, query: str, num_results: int) -> list[SearchResult]:
        results = await super().search(query, num_results)
        for result in results:
            if result.url.startswith("/link?"):
                result.url = self.base_url + result.url
                result.url = await self._parse_url(result.url)
        return results

    async def _parse_url(self, url) -> str:
        html = await self._get_html(url)
        soup = BeautifulSoup(html, "html.parser")
        script = soup.find("script")
        if script:
            script_text = (
                script.string if script.string is not None else script.get_text()
            )
            match = re.search(r'window.location.replace\("(.+?)"\)', script_text)
            if match:
                url = match.group(1)
        return url
