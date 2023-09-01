import requests
import util.general_utils as gu
from bs4 import BeautifulSoup
import time
from util.func_call import (
    FuncCall, 
    FuncCallJsonFormatError, 
    FuncNotFoundError
)
def tidy_text(text: str) -> str:
    return text.strip().replace("\n", "").replace(" ", "").replace("\r", "")

def special_fetch_zhihu(link: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) \
            AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = requests.get(link, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    if "zhuanlan.zhihu.com" in link:
        r = soup.find(class_="Post-RichTextContainer")
    else:
        r = soup.find(class_="List-item").find(class_="RichContent-inner")
    if r is None:
        print("debug: zhihu none")
        raise Exception("zhihu none")
    return tidy_text(r.text)

def web_keyword_search_via_bing(keyword) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) \
            AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    url = "https://cn.bing.com/search?q="+keyword
    _cnt = 0
    _detail_store = []
    while _cnt < 5:
        try:
            response = requests.get(url, headers=headers)
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
                    if len(_detail_store) < 2 and "zhihu.com" in link:
                        try:
                            _detail_store.append(special_fetch_zhihu(link)[:800])
                        except BaseException as e:
                            print(f"zhihu parse err: {str(e)}")
                    if len(res) >= 5: # 限制5条
                        break
                except Exception as e:
                    print(f"bing parse err: {str(e)}")
            if len(res) == 0:
                break
            if len(_detail_store) > 0:
                ret = f"{str(res)} \n来源知乎的具体资料: {str(_detail_store)}"
            else:
                ret = f"{str(res)}"
            return str(ret)
        except Exception as e:
            print(f"bing fetch err: {str(e)}")
            _cnt += 1
            time.sleep(1)
    print("fail to fetch bing info, using sougou.")
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
        except:
            pass
    ret = f"{str(res)} \n全部内容: {tidy_text(soup.text)}"
    return ret

def fetch_website_content(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) \
            AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")
    res = soup.text
    res = res.replace("\n", "")
    with open(f"temp_{time.time()}.html", "w", encoding="utf-8") as f:
        f.write(res)
    return res

def web_search(question, provider):

    new_func_call = FuncCall(provider)

    new_func_call.add_func("web_keyword_search_via_bing", [{
        "type": "string",
        "name": "keyword",
        "brief": "必应搜索的关键词(分词，尽量保留所有信息)"
        }], 
    "在必应搜索引擎上搜索给定的关键词，并且返回第一页的搜索结果列表(标题,简介和链接)",
    web_keyword_search_via_bing
    )

    func_definition1 = new_func_call.func_dump()
    question1 = f"{question} \n（只能调用一个函数。）"
    res1, has_func = new_func_call.func_call(question1, func_definition1, is_task=False, is_summary=False)
    has_func = True
    if has_func:
        provider.forget()
        question3 = f"""请你回答`{question}`问题。\n以下是相关材料，你请直接拿此材料针对问题进行总结回答，然后再给出参考链接。不要提到任何函数调用的信息。```\n{res1}\n```\n"""
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
                    question3 = f"""请你回答`{question}`问题。\n以下是相关材料，请直接拿此材料针对问题进行回答，然后再给出参考链接。```\n{res1}\n{res2}\n```\n"""
        return res3
    else:
        return res1