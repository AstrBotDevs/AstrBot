import aiohttp
import asyncio
import random
import astrbot.api.star as star
import astrbot.api.event.filter as filter
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api.provider import ProviderRequest
from astrbot.api import llm_tool, agent, logger, AstrBotConfig
from astrbot.core.provider.func_tool_manager import FunctionToolManager
from .engines import SearchResult
from .engines.bing import Bing
from .engines.sogo import Sogo
from .engines.google import Google
from readability import Document
from bs4 import BeautifulSoup
from .engines import HEADERS, USER_AGENTS


class Main(star.Star):
    TOOLS = [
        "web_search",
        "fetch_url",
        "web_search_tavily",
        "tavily_extract_web_page",
    ]

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

    async def _process_search_result(
        self, result: SearchResult, idx: int, websearch_link: bool
    ) -> str:
        """处理单个搜索结果"""
        logger.info(f"web_searcher - scraping web: {result.title} - {result.url}")
        try:
            site_result = await self._get_from_url(result.url)
        except BaseException:
            site_result = ""
        site_result = (
            f"{site_result[:700]}..." if len(site_result) > 700 else site_result
        )

        header = f"{idx}. {result.title} "

        if websearch_link and result.url:
            header += result.url

        return f"{header}\n{result.snippet}\n{site_result}\n\n"

    async def _web_search_default(
        self, query, num_results: int = 5
    ) -> list[SearchResult]:
        results = []
        try:
            results = await self.google.search(query, num_results)
        except Exception as e:
            logger.error(f"google search error: {e}, try the next one...")
        if len(results) == 0:
            logger.debug("search google failed")
            try:
                results = await self.bing_search.search(query, num_results)
            except Exception as e:
                logger.error(f"bing search error: {e}, try the next one...")
        if len(results) == 0:
            logger.debug("search bing failed")
            try:
                results = await self.sogo_search.search(query, num_results)
            except Exception as e:
                logger.error(f"sogo search error: {e}")
        if len(results) == 0:
            logger.debug("search sogo failed")
            return []

        return results

    async def _web_search_tavily(
        self, cfg: AstrBotConfig, payload: dict
    ) -> list[SearchResult]:
        """使用 Tavily 搜索引擎进行搜索"""
        tavily_key = cfg.get("provider_settings", {}).get("websearch_tavily_key", None)
        if not tavily_key:
            raise ValueError("Error: Tavily API key is not configured in AstrBot.")
        url = "https://api.tavily.com/search"
        header = {
            "Authorization": f"Bearer {tavily_key}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.post(
                url, json=payload, headers=header, timeout=6
            ) as response:
                if response.status != 200:
                    reason = await response.text()
                    raise Exception(
                        f"Tavily web search failed: {reason}, status: {response.status}"
                    )
                data = await response.json()
                results = []
                for item in data.get("results", []):
                    result = SearchResult(
                        title=item.get("title"),
                        url=item.get("url"),
                        snippet=item.get("content"),
                    )
                    results.append(result)
                return results

    async def _extract_tavily(self, cfg: AstrBotConfig, payload: dict) -> list[dict]:
        """使用 Tavily 提取网页内容"""
        tavily_key = cfg.get("provider_settings", {}).get("websearch_tavily_key", None)
        if not tavily_key:
            raise ValueError("Error: Tavily API key is not configured in AstrBot.")
        url = "https://api.tavily.com/extract"
        header = {
            "Authorization": f"Bearer {tavily_key}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.post(
                url, json=payload, headers=header, timeout=6
            ) as response:
                if response.status != 200:
                    reason = await response.text()
                    raise Exception(
                        f"Tavily web search failed: {reason}, status: {response.status}"
                    )
                data = await response.json()
                results: list[dict] = data.get("results", [])
                if not results:
                    raise ValueError(
                        "Error: Tavily web searcher does not return any results."
                    )
                return results

    @filter.command("websearch")
    async def websearch(self, event: AstrMessageEvent, oper: str = None) -> str:
        event.set_result(
            MessageEventResult().message(
                "此指令已经被废弃，请在 WebUI 中开启或关闭网页搜索功能。"
            )
        )

    @llm_tool(name="web_search")
    async def search_from_search_engine(
        self, event: AstrMessageEvent, query: str, max_results: int = 5
    ) -> str:
        """搜索网络以回答用户的问题。当用户需要搜索网络以获取即时性的信息时调用此工具。

        Args:
            query(string): 和用户的问题最相关的搜索关键词，用于在 Google 上搜索。
            max_results(number): 返回的最大搜索结果数量，默认为 5。
        """
        logger.info(f"web_searcher - search_from_search_engine: {query}")
        cfg = self.context.get_config(umo=event.unified_msg_origin)
        websearch_link = cfg["provider_settings"].get("web_search_link", False)

        results = await self._web_search_default(query, max_results)
        if not results:
            return "Error: web searcher does not return any results."

        tasks = []
        for idx, result in enumerate(results, 1):
            task = self._process_search_result(result, idx, websearch_link)
            tasks.append(task)
        processed_results = await asyncio.gather(*tasks, return_exceptions=True)
        ret = ""
        for processed_result in processed_results:
            if isinstance(processed_result, Exception):
                logger.error(f"Error processing search result: {processed_result}")
                continue
            ret += processed_result

        if websearch_link:
            ret += "\n\n针对问题，请根据上面的结果分点总结，并且在结尾处附上对应内容的参考链接（如有）。"

        return ret

    @llm_tool(name="fetch_url")
    async def fetch_website_content(self, event: AstrMessageEvent, url: str) -> str:
        """fetch the content of a website with the given web url

        Args:
            url(string): The url of the website to fetch content from
        """
        resp = await self._get_from_url(url)
        return resp

    @llm_tool("web_search_tavily")
    async def search_from_tavily(
        self,
        event: AstrMessageEvent,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
        topic: str = "general",
        days: int = 3,
        time_range: str = "",
        start_date: str = "",
        end_date: str = "",
    ) -> str:
        """A web search tool that uses Tavily to search the web for relevant content.
        Ideal for gathering current information, news, and detailed web content analysis.

        Args:
            query(string): Required. Search query.
            max_results(number): Optional. The maximum number of results to return. Default is 5. Range is 5-20.
            search_depth(string): Optional. The depth of the search, must be one of 'basic', 'advanced'. Default is "basic".
            topic(string): Optional. The topic of the search, must be one of 'general', 'news'. Default is "general".
            days(number): Optional. The number of days back from the current date to include in the search results. Please note that this feature is only available when using the 'news' search topic.
            time_range(string): Optional. The time range back from the current date to include in the search results. This feature is available for both 'general' and 'news' search topics. Must be one of 'day', 'week', 'month', 'year'.
            start_date(string): Optional. The start date for the search results in the format 'YYYY-MM-DD'.
            end_date(string): Optional. The end date for the search results in the format 'YYYY-MM-DD'.
        """
        logger.info(f"web_searcher - search_from_tavily: {query}")
        cfg = self.context.get_config(umo=event.unified_msg_origin)
        websearch_link = cfg["provider_settings"].get("web_search_link", False)
        tavily_key = cfg.get("provider_settings", {}).get("websearch_tavily_key", None)
        if not tavily_key:
            raise ValueError("Error: Tavily API key is not configured in AstrBot.")

        # build payload
        payload = {
            "query": query,
            "max_results": max_results,
        }
        if search_depth not in ["basic", "advanced"]:
            search_depth = "basic"
        payload["search_depth"] = search_depth

        if topic not in ["general", "news"]:
            topic = "general"
        payload["topic"] = topic

        if topic == "news":
            payload["days"] = days

        if time_range in ["day", "week", "month", "year"]:
            payload["time_range"] = time_range
        if start_date:
            payload["start_date"] = start_date
        if end_date:
            payload["end_date"] = end_date

        results = await self._web_search_tavily(cfg, payload)
        if not results:
            return "Error: Tavily web searcher does not return any results."

        ret_ls = []
        for result in results:
            ret_ls.append(f"\nTitle: {result.title}")
            ret_ls.append(f"URL: {result.url}")
            ret_ls.append(f"Content: {result.snippet}")
        ret = "\n".join(ret_ls)

        if websearch_link:
            ret += "\n\n针对问题，请根据上面的结果分点总结，并且在结尾处附上对应内容的参考链接（如有）。"
        return ret

    @llm_tool("tavily_extract_web_page")
    async def tavily_extract_web_page(
        self, event: AstrMessageEvent, url: str = "", extract_depth: str = "basic"
    ) -> str:
        """Extract the content of a web page using Tavily.

        Args:
            url(string): Required. An URl to extract content from.
            extract_depth(string): Optional. The depth of the extraction, must be one of 'basic', 'advanced'. Default is "basic".
        """
        cfg = self.context.get_config(umo=event.unified_msg_origin)
        tavily_key = cfg.get("provider_settings", {}).get("websearch_tavily_key", None)
        if not tavily_key:
            raise ValueError("Error: Tavily API key is not configured in AstrBot.")

        if not url:
            raise ValueError("Error: url must be a non-empty string.")
        if extract_depth not in ["basic", "advanced"]:
            extract_depth = "basic"
        payload = {
            "urls": [url],
            "extract_depth": extract_depth,
        }
        results = await self._extract_tavily(cfg, payload)
        ret_ls = []
        for result in results:
            ret_ls.append(f"URL: {result.get('url', 'No URL')}")
            ret_ls.append(f"Content: {result.get('raw_content', 'No content')}")
        ret = "\n".join(ret_ls)
        if not ret:
            return "Error: Tavily web searcher does not return any results."
        return ret

    @filter.on_llm_request(priority=-10000)
    async def edit_web_search_tools(
        self, event: AstrMessageEvent, req: ProviderRequest
    ) -> str:
        """Get the session conversation for the given event."""
        cfg = self.context.get_config(umo=event.unified_msg_origin)
        prov_settings = cfg.get("provider_settings", {})
        websearch_enable = prov_settings.get("web_search", False)
        provider = prov_settings.get("websearch_provider", "default")

        tool_set = req.func_tool
        if isinstance(tool_set, FunctionToolManager):
            req.func_tool = tool_set.get_full_tool_set()
            tool_set = req.func_tool

        if not websearch_enable:
            # pop tools
            for tool_name in self.TOOLS:
                tool_set.remove_tool(tool_name)
            return

        func_tool_mgr = self.context.get_llm_tool_manager()
        if provider == "default":
            web_search_t = func_tool_mgr.get_func("web_search")
            fetch_url_t = func_tool_mgr.get_func("fetch_url")
            if web_search_t:
                tool_set.add_tool(web_search_t)
            if fetch_url_t:
                tool_set.add_tool(fetch_url_t)
            tool_set.remove_tool("web_search_tavily")
            tool_set.remove_tool("tavily_extract_web_page")
        elif provider == "tavily":
            web_search_tavily = func_tool_mgr.get_func("web_search_tavily")
            tavily_extract_web_page = func_tool_mgr.get_func("tavily_extract_web_page")
            if web_search_tavily:
                tool_set.add_tool(web_search_tavily)
            if tavily_extract_web_page:
                tool_set.add_tool(tavily_extract_web_page)
            tool_set.remove_tool("web_search")
            tool_set.remove_tool("fetch_url")
