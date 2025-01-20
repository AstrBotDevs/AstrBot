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
from .engines.config import HEADERS, USER_AGENTS


@star.register(name="astrbot-web-searcher", desc="让 LLM 具有网页检索能力", author="Soulter", version="1.14.514")
class Main(star.Star):
    '''使用 /websearch on 或者 off 开启或者关闭网页搜索功能'''
    def __init__(self, context: star.Context) -> None:
        self.context = context
        
        self.bing_search = Bing()
        self.sogo_search = Sogo()
        self.google = Google()
        
    async def initialize(self):
        websearch = self.context.get_config()['provider_settings']['web_search']
        if websearch:
            self.context.activate_llm_tool("web_search")
            self.context.activate_llm_tool("fetch_url")
        else:
            self.context.deactivate_llm_tool("web_search")
            self.context.deactivate_llm_tool("fetch_url")
        
    async def _tidy_text(self, text: str) -> str:
        '''清理文本，去除空格、换行符等'''
        return text.strip().replace("\n", " ").replace("\r", " ").replace("  ", " ")
        
    async def _get_from_url(self, url: str) -> str:
        '''获取网页内容'''
        header = HEADERS
        header.update({'User-Agent': random.choice(USER_AGENTS)})
        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.get(url, headers=header, timeout=6) as response:
                html = await response.text(encoding="utf-8")
                doc = Document(html)
                ret = doc.summary(html_partial=True)
                soup = BeautifulSoup(ret, 'html.parser')
                ret = await self._tidy_text(soup.get_text())
                return ret

    @filter.command("websearch")
    async def websearch(self, event: AstrMessageEvent, oper: str = None) -> str:
        websearch = self.context.get_config()['provider_settings']['web_search']
        if oper is None:
            status = "开启" if websearch else "关闭"
            event.set_result(MessageEventResult().message("当前网页搜索功能状态：" + status + "。使用 /websearch on 或者 off 启用或者关闭。"))
            return
        
        if oper == "on":
            self.context.get_config()['provider_settings']['web_search'] = True
            self.context.get_config().save_config()
            self.context.activate_llm_tool("web_search")
            self.context.activate_llm_tool("fetch_url")
            event.set_result(MessageEventResult().message("已开启网页搜索功能"))
        elif oper == "off":
            self.context.get_config()['provider_settings']['web_search'] = False
            self.context.get_config().save_config()
            self.context.deactivate_llm_tool("web_search")
            self.context.deactivate_llm_tool("fetch_url")
            event.set_result(MessageEventResult().message("已关闭网页搜索功能"))
        else:
            event.set_result(MessageEventResult().message("操作参数错误，应为 on 或 off"))
            
    @llm_tool("web_search")
    async def search_from_search_engine(self, event: AstrMessageEvent, query: str) -> str:
        '''Search the web for answers to the user's query
        
        Args:
            query(string): A search query which will be used to fetch the most relevant snippets regarding the user's query
        '''
        logger.info("web_searcher - search_from_search_engine: " + query)
        results = []
        RESULT_NUM = 5
        try:
            results = await self.google.search(query, RESULT_NUM)
        except BaseException as e:
            logger.error(f"google search error: {e}, try the next one...")
        if len(results) == 0:
            logger.debug("search google failed")
            try:
                results = await self.bing_search.search(query, RESULT_NUM)
            except BaseException as e:
                logger.error(f"bing search error: {e}, try the next one...")
        if len(results) == 0:
            logger.debug("search bing failed")
            try:
                results = await self.sogo_search.search(query, RESULT_NUM)
            except BaseException as e:
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
            site_result = site_result[:700] + "..." if len(site_result) > 700 else site_result
            ret += f"{idx}. {i.title} \n{i.snippet}\n{site_result}\n\n"
            idx += 1
        
        return ret

    @llm_tool("fetch_url")
    async def fetch_website_content(self, event: AstrMessageEvent, url: str) -> str:
        '''fetch the content of a website with the given web url
        
        Args:
            url(string): The url of the website to fetch content from
        '''
        resp = await self._get_from_url(url)
        return resp