import random
import aiohttp
import os

from readability import Document
from bs4 import BeautifulSoup
from engines.config import HEADERS, USER_AGENTS
from engines.bing import Bing
from engines.sogo import Sogo
from engines.google import Google
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api.provider import Provider
from astrbot.api import logger

bing_search = Bing()
sogo_search = Sogo()
google = Google()
proxy = os.environ.get("HTTPS_PROXY", None)

def tidy_text(text: str) -> str:
    '''
    清理文本，去除空格、换行符等
    '''
    return text.strip().replace("\n", " ").replace("\r", " ").replace("  ", " ")

async def search_from_bing(keyword: str, event: AstrMessageEvent = None, provider: Provider = None) -> str:
    '''
    tools, 从 bing 搜索引擎搜索
    '''
    logger.info("web_searcher - search_from_bing: " + keyword)
    results = []
    try:
        results = await google.search(keyword, 5)
    except BaseException as e:
        logger.error(f"google search error: {e}, try the next one...")
    if len(results) == 0:
        logger.debug("search google failed")
        try:
            results = await bing_search.search(keyword, 5)
        except BaseException as e:
            logger.error(f"bing search error: {e}, try the next one...")
    if len(results) == 0:
        logger.debug("search bing failed")
        try:
            results = await sogo_search.search(keyword, 5)
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
            site_result = await fetch_website_content(i.url)
        except BaseException:
            site_result = ""
        site_result = site_result[:600] + "..." if len(site_result) > 600 else site_result
        ret += f"{idx}. {i.title} \n{i.snippet}\n{site_result}\n\n"
        idx += 1

    return await summarize(ret, event, provider)

async def fetch_website_content(url: str, event: AstrMessageEvent = None, provider: Provider = None) -> str:
    header = HEADERS
    header.update({'User-Agent': random.choice(USER_AGENTS)})
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=HEADERS, timeout=6, proxy=proxy) as response:
            html = await response.text(encoding="utf-8")
            doc = Document(html)
            ret = doc.summary(html_partial=True)
            soup = BeautifulSoup(ret, 'html.parser')
            ret = tidy_text(soup.get_text())
            return await summarize(ret, event, provider)
    
async def summarize(text: str, event: AstrMessageEvent = None, provider: Provider = None) -> str:
                
    summary_prompt = f"""
你是一个专业且高效的助手，你擅长总结给定文本。你的任务是
1. 回答用户的问题 `{event.message_str}`，用户的问题相关的材料在下方；
2. 简略发表你的看法。

# 例子
1. 从网上的信息来看，可以知道...我个人认为...
2. 根据网上的最新信息，可以得知...我觉得...

# 限制
1. 限制在 200-300 字；
2. 请**直接输出总结**，不要输出多余的内容和提示语。

# 相关材料
{text}"""
    ret = await provider.text_chat(summary_prompt, session_id=event.session_id)
    event.set_result(MessageEventResult().message(ret))