import requests
import util.general_utils as gu
from bs4 import BeautifulSoup
import time
from util.func_call import (
    FuncCall, 
    FuncCallJsonFormatError, 
    FuncNotFoundError
)
import traceback
from googlesearch import search, SearchResult

def tidy_text(text: str) -> str:
    return text.strip().replace("\n", "").replace(" ", "").replace("\r", "")

def special_fetch_zhihu(link: str) -> str:
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
    # 获取goole搜索结果，得到title、desc、link
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
                            _detail_store.append(special_fetch_zhihu(link)[100:800])
                        except BaseException as e:
                            print(f"zhihu parse err: {str(e)}")
                    else:
                        try:
                            _detail_store.append(fetch_website_content(link)[100:1000])
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
            print(traceback.format_exc())
            print(f"bing fetch err: {str(e)}")
            _cnt += 1
            time.sleep(1)
            
    print("fail to fetch bing info, using sougou.")
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
            _detail_store.append(fetch_website_content(i["link"])[100:1000])
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
    soup = BeautifulSoup(response.text, "html.parser")
    # 如果有container / content / main等的话，就只取这些部分
    has = False
    beleive_ls = ["container", "content", "main"]
    res = ""
    for cls in beleive_ls:
        for i in soup.find_all(class_=cls):
            has = True
            res += i.text
    if not has:
        res = soup.text
    res = res.replace("\n", "").replace("  ", " ").replace("\r", "").replace("\t", "")
    if not has:
        res = res[300:1100]
    else:
        res = res[100:800]
    # with open(f"temp_{time.time()}.html", "w", encoding="utf-8") as f:
    #     f.write(res)
    gu.log(f"fetch_website_content: end", tag="fetch_website_content", level=gu.LEVEL_DEBUG)
    return res

def web_search(question, provider, session_id):

    new_func_call = FuncCall(provider)
    new_func_call.add_func("google_web_search", [{
        "type": "string",
        "name": "keyword",
        "brief": "google search query (分词，尽量保留所有信息)"
        }],
    "网页搜索。如果问题需要使用搜索(如天气、新闻或任何新的东西)，则调用。",
    google_web_search
    )
    new_func_call.add_func("fetch_website_content", [{
        "type": "string",
        "name": "url",
        "brief": "网址"
        }],
    "获取网址的内容",
    fetch_website_content
    )
    func_definition1 = new_func_call.func_dump()
    question1 = f"{question} \n（只能调用一个函数。）"
    try:
        res1, has_func = new_func_call.func_call(question1, func_definition1, is_task=False, is_summary=False)
    except BaseException as e:
        res = provider.text_chat(question) + "\n(网页搜索失败, 此为默认回复)"
        return res

    has_func = True
    if has_func:
        provider.forget(session_id)
        question3 = f"""请你回答`{question}`问题。\n以下是相关材料，请直接拿此材料针对问题进行总结回答，再给参考链接, 参考链接首末有空格。不要提到任何函数调用的信息。```\n{res1}\n```\n"""
        print(question3)
        _c = 0
        while _c < 5:
            try:
                print('text chat')
                res3 = provider.text_chat(question3)
                break
            except Exception as e:
                print(e)
                _c += 1
                if _c == 5:
                    raise e
                if "The message you submitted was too long" in str(e):
                    res2 = res2[:int(len(res2) / 2)]
                    time.sleep(3)
                    question3 = f"""请回答`{question}`问题。\n以下是相关材料，请直接拿此材料针对问题进行回答，再给参考链接, 参考链接首末有空格。```\n{res1}\n{res2}\n```\n"""
        return res3
    else:
        return res1