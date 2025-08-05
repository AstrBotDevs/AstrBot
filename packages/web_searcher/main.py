import aiohttp
import random
import astrbot.api.star as star
import astrbot.api.event.filter as filter
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api import llm_tool, logger
from .engines.bing import Bing
from .engines.sogo import Sogo
from .engines.google import Google
from readability import Document
from bs4 import BeautifulSoup
from .engines import HEADERS, USER_AGENTS


class Main(star.Star):
    """使用 /websearch on 或者 off 开启或者关闭网页搜索功能"""

    def __init__(self, context: star.Context) -> None:
        self.context = context

        self.bing_search = Bing()
        self.sogo_search = Sogo()
        self.google = Google()

    async def _tidy_text(self, text: str) -> str:
        """清理文本，去除空格、换行符等"""
        return text.strip().replace("\n", " ").replace("\r", " ").replace("  ", " ")

    async def _get_from_url(self, url: str) -> str:
        """获取网页内容"""
        header = HEADERS
        header.update({"User-Agent": random.choice(USER_AGENTS)})
        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.get(url, headers=header, timeout=6) as response:
                html = await response.text(encoding="utf-8")
                doc = Document(html)
                ret = doc.summary(html_partial=True)
                soup = BeautifulSoup(ret, "html.parser")
                ret = await self._tidy_text(soup.get_text())
                return ret

    @filter.command("websearch")
    async def websearch(self, event: AstrMessageEvent, oper: str = None) -> str:
        event.set_result(MessageEventResult().message("此指令已经被废弃，请在 WebUI 中开启或关闭网页搜索功能。"))

    @llm_tool("web_search")
    async def search_from_search_engine(
        self, event: AstrMessageEvent, query: str
    ) -> str:
        """搜索网络以回答用户的问题。当用户需要搜索网络以获取即时性的信息时调用此工具。

        Args:
            query(string): 和用户的问题最相关的搜索关键词，用于在 Google 上搜索。
        """
        logger.info("web_searcher - search_from_search_engine: " + query)
        websearch_link = self.context.get_config(umo=event.unified_msg_origin)[
            "provider_settings"
        ].get("web_search_link", False)
        results = []
        RESULT_NUM = 5
        try:
            results = await self.google.search(query, RESULT_NUM)
        except Exception as e:
            logger.error(f"google search error: {e}, try the next one...")
        if len(results) == 0:
            logger.debug("search google failed")
            try:
                results = await self.bing_search.search(query, RESULT_NUM)
            except Exception as e:
                logger.error(f"bing search error: {e}, try the next one...")
        if len(results) == 0:
            logger.debug("search bing failed")
            try:
                results = await self.sogo_search.search(query, RESULT_NUM)
            except Exception as e:
                logger.error(f"sogo search error: {e}")
        if len(results) == 0:
            logger.debug("search sogo failed")
            return "没有搜索到结果"
        ret = ""
        idx = 1
        for i in results:
            logger.info(f"web_searcher - scraping web: {i.title} - {i.url}")
            try:
                site_result = await self._get_from_url(i.url)
            except BaseException:
                site_result = ""
            site_result = (
                site_result[:700] + "..." if len(site_result) > 700 else site_result
            )

            header = f"{idx}. {i.title} "

            if websearch_link and i.url:
                header += i.url

            ret += f"{header}\n{i.snippet}\n{site_result}\n\n"
            idx += 1

        if websearch_link:
            ret += "针对问题，请根据上面的结果分点总结，并且在结尾处附上对应内容的参考链接（如有）。"

        return ret

    @llm_tool("fetch_url")
    async def fetch_website_content(self, event: AstrMessageEvent, url: str) -> str:
        """fetch the content of a website with the given web url

        Args:
            url(string): The url of the website to fetch content from
        """
        resp = await self._get_from_url(url)
        return resp
