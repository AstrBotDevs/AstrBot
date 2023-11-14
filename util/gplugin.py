import requests
import util.general_utils as gu
from bs4 import BeautifulSoup
import time
from util.func_call import (
    FuncCall, 
    FuncCallJsonFormatError, 
    FuncNotFoundError
)
from openai.types.chat.chat_completion_message_tool_call import Function
import traceback
from googlesearch import search, SearchResult
from model.provider.provider import Provider
import json
from readability import Document


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
                desc = fetch_website_content(i.url)
            except BaseException as e:
                print(f"(google) fetch_website_content err: {str(e)}")
            gu.log(f"# No.{str(index)}\ntitle: {i.title}\nurl: {i.url}\ncontent: {desc}\n\n", level=gu.LEVEL_DEBUG, max_len=9999)
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
    _detail_store = []
    while _cnt < 5:
        try:
            response = requests.get(url, headers=headers)
            response.encoding = "utf-8"
            gu.log(f"bing response: {response.text}", tag="bing", level=gu.LEVEL_DEBUG, max_len=9999)
            soup = BeautifulSoup(response.text, "html.parser")
            res = []
            ols = soup.find(id="b_results")
            for i in ols.find_all("li", class_="b_algo"):
                try:
                    title = i.find("h2").text
                    desc = i.find("p").text
                    link = i.find("h2").find("a").get("href")
                    res.append({
                        "title": title,
                        "desc": desc,
                        "link": link,
                    })
                    if len(res) >= 5: # 限制5条
                        break
                    if len(_detail_store) >= 3:
                        continue

                    # 爬取前两条的网页内容
                    if "zhihu.com" in link:
                        try:
                            _detail_store.append(special_fetch_zhihu(link))
                        except BaseException as e:
                            print(f"zhihu parse err: {str(e)}")
                    else:
                        try:
                            _detail_store.append(fetch_website_content(link))
                        except BaseException as e:
                            print(f"fetch_website_content err: {str(e)}")

                except Exception as e:
                    print(f"bing parse err: {str(e)}")
            if len(res) == 0:
                break
            if len(_detail_store) > 0:
                ret = f"{str(res)} \n具体网页内容: {str(_detail_store)}"
            else:
                ret = f"{str(res)}"
            return str(ret)
        except Exception as e:
            gu.log(f"bing fetch err: {str(e)}")
            _cnt += 1
            time.sleep(1)
            
    gu.log("fail to fetch bing info, using sougou.")
    return google_web_search(keyword)

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
            if len(res) >= 5: # 限制5条
                break
        except Exception as e:
            gu.log(f"sougou parse err: {str(e)}", tag="web_keyword_search_via_sougou", level=gu.LEVEL_ERROR)
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
    gu.log(f"fetch_website_content: {url}", tag="fetch_website_content", level=gu.LEVEL_DEBUG)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) \
            AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = requests.get(url, headers=headers, timeout=3)
    response.encoding = "utf-8"
    # soup = BeautifulSoup(response.text, "html.parser")
    # # 如果有container / content / main等的话，就只取这些部分
    # has = False
    # beleive_ls = ["container", "content", "main"]
    # res = ""
    # for cls in beleive_ls:
    #     for i in soup.find_all(class_=cls):
    #         has = True
    #         res += i.text
    # if not has:
    #     res = soup.text
    # res = res.replace("\n", "").replace("  ", " ").replace("\r", "").replace("\t", "")
    # if not has:
    #     res = res[300:1100]
    # else:
    #     res = res[100:800]
    # # with open(f"temp_{time.time()}.html", "w", encoding="utf-8") as f:
    # #     f.write(res)
    # gu.log(f"fetch_website_content: end", tag="fetch_website_content", level=gu.LEVEL_DEBUG)
    # return res
    doc = Document(response.content)
    # print('title:', doc.title())
    ret = doc.summary(html_partial=True)
    soup = BeautifulSoup(ret, 'html.parser')
    ret = tidy_text(soup.get_text())
    return ret

def web_search(question, provider: Provider, session_id, official_fc=False):
    '''
    official_fc: 使用官方 function-calling
    '''
    new_func_call = FuncCall(provider)
    new_func_call.add_func("google_web_search", [{
        "type": "string",
        "name": "keyword",
        "description": "google search query (分词，尽量保留所有信息)"
        }],
    "通过搜索引擎搜索。如果问题需要在网页上搜索(如天气、新闻或任何需要通过网页获取信息的问题)，则调用此函数；如果没有，不要调用此函数。",
    google_web_search
    )
    new_func_call.add_func("fetch_website_content", [{
        "type": "string",
        "name": "url",
        "description": "网址"
        }],
    "获取网页的内容。如果问题带有合法的网页链接(例如: `帮我总结一下https://github.com的内容`), 就调用此函数。如果没有，不要调用此函数。",
    fetch_website_content
    )
    question1 = f"{question} \n> hint: 最多只能调用1个function, 并且存在不会调用任何function的可能性。"
    has_func = False
    function_invoked_ret = ""
    if official_fc:
        func = provider.text_chat(question1, session_id, function_call=new_func_call.get_func())
        if isinstance(func, Function):
            # arguments='{\n  "keyword": "北京今天的天气"\n}', name='google_web_search'
            # 执行对应的结果：
            func_obj = None
            for i in new_func_call.func_list:
                if i["name"] == func.name:
                    func_obj = i["func_obj"]
                    break
            if not func_obj:
                gu.log("找不到返回的 func name " + func.name, level=gu.LEVEL_ERROR)
                return provider.text_chat(question1, session_id) + "\n(网页搜索失败, 此为默认回复)"
            try:
                args = json.loads(func.arguments)
                function_invoked_ret = func_obj(**args)
                has_func = True
            except BaseException as e:
                traceback.print_exc()
                return provider.text_chat(question1, session_id) + "\n(网页搜索失败, 此为默认回复)"
        else:
            # now func is a string
            return func
    else:
        try:
            function_invoked_ret, has_func = new_func_call.func_call(question1, new_func_call.func_dump(), is_task=False, is_summary=False)
        except BaseException as e:
            res = provider.text_chat(question) + "\n(网页搜索失败, 此为默认回复)"
            return res
        has_func = True

    if has_func:
        provider.forget(session_id)
        question3 = f"""请你用活泼的语气回答`{question}`问题。\n以下是相关材料，请直接拿此材料针对问题进行总结回答。在引文末加上参考链接的标号，如` [1]`；在文章末尾加上各参考链接，如`[1] <标题> <网址>`；不要提到任何函数调用的信息；在总结的末尾加上 1-2 个相关的emoji。```\n{function_invoked_ret}\n```\n"""
        gu.log(f"web_search: {question3}", tag="web_search", level=gu.LEVEL_DEBUG, max_len=99999)
        _c = 0
        while _c < 3:
            try:
                print('text chat')
                final_ret = provider.text_chat(question3)
                return final_ret
            except Exception as e:
                print(e)
                _c += 1
                if _c == 3: raise e
                if "The message you submitted was too long" in str(e):
                    provider.forget(session_id)
                    function_invoked_ret = function_invoked_ret[:int(len(function_invoked_ret) / 2)]
                    time.sleep(3)
                    question3 = f"""请回答`{question}`问题。\n以下是相关材料，请直接拿此材料针对问题进行回答，再给参考链接, 参考链接首末有空格。```\n{function_invoked_ret}\n```\n"""
    return function_invoked_ret
