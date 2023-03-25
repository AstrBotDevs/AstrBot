import asyncio
from EdgeGPT import Chatbot, ConversationStyle
import json

class revEdgeGPT:
    def __init__(self):
        with open('./cookies.json', 'r') as f:
            cookies = json.load(f)
        self.bot = Chatbot(cookies=cookies)

    async def chat(self, prompt):
        resp = 'err'
        err_count = 0
        retry_count = 5
        
        while err_count < retry_count:
            try:
                resp = await self.bot.ask(prompt=prompt, conversation_style=ConversationStyle.creative)
                resp = resp['item']['messages'][len(resp['item']['messages'])-1]['text']
                break
            except BaseException as e:
                err_count += 1
                if err_count >= retry_count:
                        raise e
                print("[RevEdgeGPT] 请求出现了一些问题, 正在重试。次数"+str(err_count))
        
        print("[RevEdgeGPT] "+str(resp))
        return resp