import random
from bs4 import BeautifulSoup
from aiohttp import ClientSession
from dataclasses import dataclass
from typing import List
import urllib.parse

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 6.1; rv:84.0) Gecko/20100101 Firefox/84.0",
    "Accept": "*/*",
    "Connection": "keep-alive",
    "Accept-Language": "en-GB,en;q=0.5",
}

USER_AGENT_BING = "Mozilla/5.0 (Windows NT 6.1; rv:84.0) Gecko/20100101 Firefox/84.0"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:88.0) Gecko/20100101 Firefox/88.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Version/14.1.2 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Version/14.1 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:88.0) Gecko/20100101 Firefox/88.0",
]


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str

    def __str__(self) -> str:
        return f"{self.title} - {self.url}\n{self.snippet}"


class SearchEngine:
    """
    搜索引擎爬虫基类
    """

    def __init__(self) -> None:
        self.TIMEOUT = 10
        self.page = 1
        self.headers = HEADERS

    def _set_selector(self, selector: str) -> None:
        raise NotImplementedError()

    def _get_next_page(self):
        raise NotImplementedError()

    async def _get_html(self, url: str, data: dict = None) -> str:
        headers = self.headers
        headers["Referer"] = url
        headers["User-Agent"] = random.choice(USER_AGENTS)
        if data:
            async with ClientSession() as session:
                async with session.post(
                    url, headers=headers, data=data, timeout=self.TIMEOUT
                ) as resp:
                    ret = await resp.text(encoding="utf-8")
                    return ret
        else:
            async with ClientSession() as session:
                async with session.get(
                    url, headers=headers, timeout=self.TIMEOUT
                ) as resp:
                    ret = await resp.text(encoding="utf-8")
                    return ret

    def tidy_text(self, text: str) -> str:
        """
        清理文本，去除空格、换行符等
        """
        return text.strip().replace("\n", " ").replace("\r", " ").replace("  ", " ")

    async def search(self, query: str, num_results: int) -> List[SearchResult]:
        query = urllib.parse.quote(query)

        try:
            resp = await self._get_next_page(query)
            soup = BeautifulSoup(resp, "html.parser")
            links = soup.select(self._set_selector("links"))
            results = []
            for link in links:
                title = self.tidy_text(
                    link.select_one(self._set_selector("title")).text
                )
                url = link.select_one(self._set_selector("url"))
                snippet = ""
                if title and url:
                    results.append(SearchResult(title=title, url=url, snippet=snippet))
            return results[:num_results] if len(results) > num_results else results
        except Exception as e:
            raise e
