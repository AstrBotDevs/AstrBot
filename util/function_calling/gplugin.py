import requests
import util.general_utils as gu
import traceback
import time
import json
import asyncio
from googlesearch import search, SearchResult
from readability import Document
from bs4 import BeautifulSoup
from openai.types.chat.chat_completion_message_tool_call import Function
from util.function_calling.func_call import (
    FuncCall,
    FuncCallJsonFormatError,
    FuncNotFoundError
)
from model.provider.provider import Provider


def tidy_text(text: str) -> str:
    '''
    清理文本，去除空格、换行符等
    '''
    return text.strip().replace("\n", " ").replace("\r", " ").replace("  ", " ")


def special_fetch_zhihu(link: str) -> str:
    '''
    function-calling 函数, 用于获取知乎文章的内容
    '''
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) \
            AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = requests.get(link, headers=headers)
    response.encoding = "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")

    if "zhuanlan.zhihu.com" in link:
        r = soup.find(class_="Post-RichTextContainer")
    else:
        r = soup.find(class_="List-item").find(class_="RichContent-inner")
    if r is None:
        print("debug: zhihu none")
        raise Exception("zhihu none")
    return tidy_text(r.text)


def google_web_search(keyword) -> str:
    '''
    获取 google 搜索结果, 得到 title、desc、link
    '''
    ret = ""
    index = 1
    try:
        ls = search(keyword, advanced=True, num_results=4)
        for i in ls:
            desc = i.description
            try:
                # gu.log(f"搜索网页: {i.url}", tag="网页搜索", level=gu.LEVEL_INFO)
                desc = fetch_website_content(i.url)
            except BaseException as e:
                print(f"(google) fetch_website_content err: {str(e)}")
            # gu.log(f"# No.{str(index)}\ntitle: {i.title}\nurl: {i.url}\ncontent: {desc}\n\n", level=gu.LEVEL_DEBUG, max_len=9999)
            ret += f"# No.{str(index)}\ntitle: {i.title}\nurl: {i.url}\ncontent: {desc}\n\n"
            index += 1
    except Exception as e:
        print(f"google search err: {str(e)}")
        return web_keyword_search_via_bing(keyword)
    return ret


def web_keyword_search_via_bing(keyword) -> str:
    '''
    获取bing搜索结果, 得到 title、desc、link
    '''
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) \
            AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    url = "https://www.bing.com/search?q="+keyword
    _cnt = 0
    # _detail_store = []
    while _cnt < 5:
        try:
            response = requests.get(url, headers=headers)
            response.encoding = "utf-8"
            # gu.log(f"bing response: {response.text}", tag="bing", level=gu.LEVEL_DEBUG, max_len=9999)
            soup = BeautifulSoup(response.text, "html.parser")
            res = ""
            result_cnt = 0
            ols = soup.find(id="b_results")
            for i in ols.find_all("li", class_="b_algo"):
                try:
                    title = i.find("h2").text
                    desc = i.find("p").text
                    link = i.find("h2").find("a").get("href")
                    # res.append({
                    #     "title": title,
                    #     "desc": desc,
                    #     "link": link,
                    # })
                    try:
                        # gu.log(f"搜索网页: {link}", tag="网页搜索", level=gu.LEVEL_INFO)
                        desc = fetch_website_content(link)
                    except BaseException as e:
                        print(f"(bing) fetch_website_content err: {str(e)}")

                    res += f"# No.{str(result_cnt + 1)}\ntitle: {title}\nurl: {link}\ncontent: {desc}\n\n"
                    result_cnt += 1
                    if result_cnt > 5:
                        break

                    # if len(_detail_store) >= 3:
                    #     continue
                    # # 爬取前两条的网页内容
                    # if "zhihu.com" in link:
                    #     try:
                    #         _detail_store.append(special_fetch_zhihu(link))
                    #     except BaseException as e:
                    #         print(f"zhihu parse err: {str(e)}")
                    # else:
                    #     try:
                    #         _detail_store.append(fetch_website_content(link))
                    #     except BaseException as e:
                    #         print(f"fetch_website_content err: {str(e)}")

                except Exception as e:
                    print(f"bing parse err: {str(e)}")
            if result_cnt == 0:
                break
            return res
        except Exception as e:
            # gu.log(f"bing fetch err: {str(e)}")
            _cnt += 1
            time.sleep(1)

    # gu.log("fail to fetch bing info, using sougou.")
    return web_keyword_search_via_sougou(keyword)


def web_keyword_search_via_sougou(keyword) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) \
            AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    }
    url = f"https://sogou.com/web?query={keyword}"
    response = requests.get(url, headers=headers)
    response.encoding = "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")

    res = []
    results = soup.find("div", class_="results")
    for i in results.find_all("div", class_="vrwrap"):
        try:
            title = tidy_text(i.find("h3").text)
            link = tidy_text(i.find("h3").find("a").get("href"))
            if link.startswith("/link?url="):
                link = "https://www.sogou.com" + link
            res.append({
                "title": title,
                "link": link,
            })
            if len(res) >= 5:  # 限制5条
                break
        except Exception as e:
            pass
            # gu.log(f"sougou parse err: {str(e)}", tag="web_keyword_search_via_sougou", level=gu.LEVEL_ERROR)
    # 爬取网页内容
    _detail_store = []
    for i in res:
        if _detail_store >= 3:
            break
        try:
            _detail_store.append(fetch_website_content(i["link"]))
        except BaseException as e:
            print(f"fetch_website_content err: {str(e)}")
    ret = f"{str(res)}"
    if len(_detail_store) > 0:
        ret += f"\n网页内容: {str(_detail_store)}"
    return ret


def fetch_website_content(url):
    # gu.log(f"fetch_website_content: {url}", tag="fetch_website_content", level=gu.LEVEL_DEBUG)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) \
            AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = requests.get(url, headers=headers, timeout=3)
    response.encoding = "utf-8"
    doc = Document(response.content)
    # print('title:', doc.title())
    ret = doc.summary(html_partial=True)
    soup = BeautifulSoup(ret, 'html.parser')
    ret = tidy_text(soup.get_text())
    return ret


async def web_search(question, provider: Provider, session_id, official_fc=False):
    '''
    official_fc: 使用官方 function-calling
    '''
    new_func_call = FuncCall(provider)
    new_func_call.add_func("google_web_search", [{
        "type": "string",
        "name": "keyword",
        "description": "google search query (分词，尽量保留所有信息)"
    }],
        "通过搜索引擎搜索。如果问题需要获取近期、实时的消息，在网页上搜索(如天气、新闻或任何需要通过网页获取信息的问题)，则调用此函数；如果没有，不要调用此函数。",
        web_keyword_search_via_bing
    )
    new_func_call.add_func("fetch_website_content", [{
        "type": "string",
        "name": "url",
        "description": "网址"
    }],
        "获取网页的内容。如果问题带有合法的网页链接(例如: `帮我总结一下 https://github.com 的内容`), 就调用此函数。如果没有，不要调用此函数。",
        fetch_website_content
    )
    question1 = f"{question} \n> hint: 最多只能调用1个function, 并且存在不会调用任何function的可能性。"
    has_func = False
    function_invoked_ret = ""
    if official_fc:
        # we use official function-calling
        func = await provider.text_chat(question1, session_id, function_call=new_func_call.get_func())
        if isinstance(func, Function):
            # 执行对应的结果：
            func_obj = None
            for i in new_func_call.func_list:
                if i["name"] == func.name:
                    func_obj = i["func_obj"]
                    break
            if not func_obj:
                # gu.log("找不到返回的 func name " + func.name, level=gu.LEVEL_ERROR)
                return await provider.text_chat(question1, session_id) + "\n(网页搜索失败, 此为默认回复)"
            try:
                args = json.loads(func.arguments)
                # we use to_thread to avoid blocking the event loop
                function_invoked_ret = await asyncio.to_thread(func_obj, **args)
                has_func = True
            except BaseException as e:
                traceback.print_exc()
                return await provider.text_chat(question1, session_id) + "\n(网页搜索失败, 此为默认回复)"
        else:
            # now func is a string
            return func
    else:
        # we use our own function-calling
        try:
            args = {
                'question': question1,
                'func_definition': new_func_call.func_dump(),
                'is_task': False,
                'is_summary': False,
            }
            function_invoked_ret, has_func = await asyncio.to_thread(new_func_call.func_call, **args)
        except BaseException as e:
            res = await provider.text_chat(question) + "\n(网页搜索失败, 此为默认回复)"
            return res
        has_func = True

    if has_func:
        await provider.forget(session_id)
        question3 = f"""
你的任务是：
1. 根据末尾的材料对问题`{question}`做切题的总结（详细）;
2. 简单地发表你对这个问题的看法（简略）。
你的总结末尾应当有对材料的引用, 如果有链接, 请在末尾附上引用网页链接。引用格式严格按照 `\n[1] title url \n`。
不要提到任何函数调用的信息。

一些回复的消息模板：
模板1:
```
从网上的信息来看，可以知道...我个人认为...你觉得呢？
```
模板2:
```
根据网上的最新信息，可以得知...我觉得...你怎么看？
```
你可以根据这些模板来组织回答，但可以不照搬，要根据问题的内容来回答。

以下是相关材料：
"""
        _c = 0
        while _c < 3:
            try:
                print('text chat')
                final_ret = await provider.text_chat(question3 + "```" + function_invoked_ret + "```", session_id)
                return final_ret
            except Exception as e:
                print(e)
                _c += 1
                if _c == 3:
                    raise e
                if "The message you submitted was too long" in str(e):
                    await provider.forget(session_id)
                    function_invoked_ret = function_invoked_ret[:int(
                        len(function_invoked_ret) / 2)]
                    time.sleep(3)
    return function_invoked_ret
