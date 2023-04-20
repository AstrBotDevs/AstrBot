from model.provider.provider import Provider
from EdgeGPT import Chatbot, ConversationStyle
import json

class ProviderRevEdgeGPT(Provider):
    def __init__(self):
        self.busy = False
        self.wait_stack = []
        with open('./cookies.json', 'r') as f:
            cookies = json.load(f)
        self.bot = Chatbot(cookies=cookies)

    def is_busy(self):
        return self.busy

    async def forget(self):
        try:
            await self.bot.reset()
            return True
        except BaseException:
            return False
        
    async def text_chat(self, prompt):
        if self.busy:
             return
        self.busy = True
        resp = 'err'
        err_count = 0
        retry_count = 5
        
        while err_count < retry_count:
            try:
                resp = await self.bot.ask(prompt=prompt, conversation_style=ConversationStyle.creative)
                # print("[RevEdgeGPT] "+str(resp))
                if 'messages' not in resp['item']:
                    await self.bot.reset()
                msj_obj = resp['item']['messages'][len(resp['item']['messages'])-1]
                reply_msg = msj_obj['text']
                if 'sourceAttributions' in msj_obj:
                    reply_source = msj_obj['sourceAttributions']
                else:
                    reply_source = []
                if 'throttling' in resp['item']:
                    throttling = resp['item']['throttling']
                    # print(throttling)
                else:
                    throttling = None
                if 'I\'m sorry but I prefer not to continue this conversation. I\'m still learning so I appreciate your understanding and patience.' in resp:
                    self.busy = False
                    return '', 0
                if reply_msg == prompt:
                    # resp += '\n\n如果你没有让我复述你的话，那代表我可能不想和你继续这个话题了，请输入reset重置会话😶'
                    await self.forget()
                    err_count += 1
                    continue
                if reply_msg is None:
                    # 不想答复
                    return '', 0
                else:
                    index = 1
                    if len(reply_source) > 0:
                        reply_msg += "\n\n信息来源:\n"
                    for i in reply_source:
                        reply_msg += f"[{str(index)}]: {i['seeMoreUrl']} | {i['providerDisplayName']}\n"
                        index += 1
                if throttling is not None:
                    reply_msg += f"\n⌈{throttling['numUserMessagesInConversation']}/{throttling['maxNumUserMessagesInConversation']}⌋"
                break
            except BaseException as e:
                # raise e
                print(e)
                err_count += 1
                if err_count >= retry_count:
                        self.busy = False
                        raise e
                print("[RevEdgeGPT] 请求出现了一些问题, 正在重试。次数"+str(err_count))
        self.busy = False
        
        print("[RevEdgeGPT] "+str(reply_msg))
        return reply_msg, 1
    
