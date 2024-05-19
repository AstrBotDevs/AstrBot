from sogo import Sogo
from bing import Bing

sogo_search = Sogo()
bing_search = Bing()
async def search(keyword: str) -> str:
    results = await sogo_search.search(keyword, 5)
    # results = await bing_search.search(keyword, 5)
    ret = ""
    if len(results) == 0:
        return "没有搜索到结果"
    
    idx = 1
    for i in results:
        ret += f"{idx}. {i.title}({i.url})\n{i.snippet}\n\n"
        idx += 1

    return ret

import asyncio
ret = asyncio.run(search("gpt4orelease"))
print(ret)