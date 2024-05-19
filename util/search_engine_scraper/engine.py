import random
try:
    from util.search_engine_scraper.config import HEADERS, USER_AGENTS
except ImportError:
    from config import HEADERS, USER_AGENTS

from bs4 import BeautifulSoup
from aiohttp import ClientSession
from dataclasses import dataclass
from typing import List


@dataclass
class SearchResult():
    title: str
    url: str
    snippet: str

    def __str__(self) -> str:
        return f"{self.title} - {self.url}\n{self.snippet}"

class SearchEngine():
    '''
    搜索引擎爬虫基类
    '''

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
                async with session.post(url, headers=headers, data=data, timeout=self.TIMEOUT) as resp:
                    return await resp.text(encoding="utf-8")
        else:
            async with ClientSession() as session:
                async with session.get(url, headers=headers, timeout=self.TIMEOUT) as resp:
                    return await resp.text(encoding="utf-8")
                
    
    def tidy_text(self, text: str) -> str:
        '''
        清理文本，去除空格、换行符等
        '''
        return text.strip().replace("\n", " ").replace("\r", " ").replace("  ", " ")


    async def search(self, query: str, num_results: int) -> List[SearchResult]:
        try:
            resp = await self._get_next_page(query)
            soup = BeautifulSoup(resp, 'html.parser')
            links = soup.select(self._set_selector('links'))
            results = []
            for link in links:
                title = self.tidy_text(link.select_one(self._set_selector('title')).text)
                url = link.select_one(self._set_selector('url'))
                snippet = ''
                if title and url:
                    results.append(SearchResult(title=title, url=url, snippet=snippet))
            return results[:num_results] if len(results) > num_results else results
        except Exception as e:
            raise e