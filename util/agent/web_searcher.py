import traceback
import random
import json
import asyncio
import aiohttp
import os

from readability import Document
from bs4 import BeautifulSoup
from openai.types.chat.chat_completion_message_tool_call import Function
from util.agent.func_call import FuncCall
from util.search_engine_scraper.config import HEADERS, USER_AGENTS
from util.search_engine_scraper.bing import Bing
from util.search_engine_scraper.sogo import Sogo
from util.search_engine_scraper.google import Google
from model.provider.provider import Provider
from SparkleLogging.utils.core import LogManager
from logging import Logger

logger: Logger = LogManager.GetLogger(log_name='astrbot-core')


bing_search = Bing()
sogo_search = Sogo()
google = Google()
proxy = os.environ.get("HTTPS_PROXY", None)

def tidy_text(text: str) -> str:
    '''
    清理文本，去除空格、换行符等
    '''
    return text.strip().replace("\n", " ").replace("\r", " ").replace("  ", " ")

# def special_fetch_zhihu(link: str) -> str:
#     '''
#     function-calling 函数, 用于获取知乎文章的内容
#     '''
#     response = requests.get(link, headers=HEADERS)
#     response.encoding = "utf-8"
#     soup = BeautifulSoup(response.text, "html.parser")

#     if "zhuanlan.zhihu.com" in link:
#         r = soup.find(class_="Post-RichTextContainer")
#     else:
#         r = soup.find(class_="List-item").find(class_="RichContent-inner")
#     if r is None:
#         print("debug: zhihu none")
#         raise Exception("zhihu none")
#     return tidy_text(r.text)

async def search_from_bing(keyword: str) -> str:
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
    return ret


async def fetch_website_content(url):
    header = HEADERS
    header.update({'User-Agent': random.choice(USER_AGENTS)})
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=HEADERS, timeout=6, proxy=proxy) as response:
            html = await response.text(encoding="utf-8")
            doc = Document(html)
            ret = doc.summary(html_partial=True)
            soup = BeautifulSoup(ret, 'html.parser')
            ret = tidy_text(soup.get_text())
            return ret


async def web_search(prompt, provider: Provider, session_id, official_fc=False):
    '''
    official_fc: 使用官方 function-calling
    '''
    new_func_call = FuncCall(provider)

    new_func_call.add_func("web_search", [{
        "type": "string",
        "name": "keyword",
        "description": "搜索关键词"
    }],
        "通过搜索引擎搜索。如果问题需要获取近期、实时的消息，在网页上搜索(如天气、新闻或任何需要通过网页获取信息的问题)，则调用此函数；如果没有，不要调用此函数。",
        search_from_bing
    )
    new_func_call.add_func("fetch_website_content", [{
        "type": "string",
        "name": "url",
        "description": "要获取内容的网页链接"
    }],
        "获取网页的内容。如果问题带有合法的网页链接并且用户有需求了解网页内容(例如: `帮我总结一下 https://github.com 的内容`), 就调用此函数。如果没有，不要调用此函数。",
        fetch_website_content
    )
    
    has_func = False
    function_invoked_ret = ""
    if official_fc:
        # we use official function-calling
        result = await provider.text_chat(prompt, session_id, tools=new_func_call.get_func())
        if isinstance(result, Function):
            logger.debug(f"web_searcher - function-calling: {result}")
            func_obj = None
            for i in new_func_call.func_list:
                if i["name"] == result.name:
                    func_obj = i["func_obj"]
                    break
            if not func_obj:
                return await provider.text_chat(prompt, session_id) + "\n(网页搜索失败, 此为默认回复)"
            try:
                args = json.loads(result.arguments)
                function_invoked_ret = await func_obj(**args)
                has_func = True
            except BaseException as e:
                traceback.print_exc()
                return await provider.text_chat(prompt, session_id) + "\n(网页搜索失败, 此为默认回复)"
        else:
            return result
    else:
        # we use our own function-calling
        try:
            args = {
                'question': prompt,
                'func_definition': new_func_call.func_dump(),
                'is_task': False,
                'is_summary': False,
            }
            function_invoked_ret, has_func = await asyncio.to_thread(new_func_call.func_call, **args)
        except BaseException as e:
            res = await provider.text_chat(prompt) + "\n(网页搜索失败, 此为默认回复)"
            return res
        has_func = True

    if has_func:
        await provider.forget(session_id)
        summary_prompt = f"""
你是一个专业且高效的助手，你的任务是
1. 根据下面的相关材料对用户的问题 `{prompt}` 进行总结;
2. 简单地发表你对这个问题的简略看法。

# 例子
1. 从网上的信息来看，可以知道...我个人认为...你觉得呢？
2. 根据网上的最新信息，可以得知...我觉得...你怎么看？

# 限制
1. 限制在 200 字以内；
2. 请**直接输出总结**，不要输出多余的内容和提示语。
        
# 相关材料
{function_invoked_ret}"""
        ret = await provider.text_chat(summary_prompt, session_id)
        return ret
    return function_invoked_ret
