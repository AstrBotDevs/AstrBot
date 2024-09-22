import random
import aiohttp
import os

from readability import Document
from bs4 import BeautifulSoup
from openai.types.chat.chat_completion_message_tool_call import Function
from openai._exceptions import *
from util.agent.func_call import FuncCall
from util.websearch.config import HEADERS, USER_AGENTS
from util.websearch.bing import Bing
from util.websearch.sogo import Sogo
from util.websearch.google import Google
from model.provider.provider import Provider
from util.log import LogManager
from logging import Logger
from type.types import Context
from type.message_event import AstrMessageEvent

logger: Logger = LogManager.GetLogger(log_name='astrbot')


bing_search = Bing()
sogo_search = Sogo()
google = Google()
proxy = os.environ.get("HTTPS_PROXY", None)

def tidy_text(text: str) -> str:
    '''
    清理文本，去除空格、换行符等
    '''
    return text.strip().replace("\n", " ").replace("\r", " ").replace("  ", " ")

async def search_from_bing(context: Context, ame: AstrMessageEvent, keyword: str) -> str:
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
        except:
            site_result = ""
        site_result = site_result[:600] + "..." if len(site_result) > 600 else site_result
        ret += f"{idx}. {i.title} \n{i.snippet}\n{site_result}\n\n"
        idx += 1

    return await summarize(context, ame, ret)


async def fetch_website_content(context: Context, ame: AstrMessageEvent, url: str):
    header = HEADERS
    header.update({'User-Agent': random.choice(USER_AGENTS)})
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=HEADERS, timeout=6, proxy=proxy) as response:
            html = await response.text(encoding="utf-8")
            doc = Document(html)
            ret = doc.summary(html_partial=True)
            soup = BeautifulSoup(ret, 'html.parser')
            ret = tidy_text(soup.get_text())
            return await summarize(context, ame, ret)
    
async def summarize(context: Context, ame: AstrMessageEvent, text: str):
                
    summary_prompt = f"""
你是一个专业且高效的助手，你的任务是
1. 根据下面的相关材料对用户的问题 `{ame.message_str}` 进行总结;
2. 简单地发表你对这个问题的看法。

# 例子
1. 从网上的信息来看，可以知道...我个人认为...你觉得呢？
2. 根据网上的最新信息，可以得知...我觉得...你怎么看？

# 限制
1. 限制在 200-300 字；
2. 请**直接输出总结**，不要输出多余的内容和提示语。

# 相关材料
{text}"""
    
    provider = context.get_current_llm_provider()
    return await provider.text_chat(prompt=summary_prompt, session_id=ame.session_id)