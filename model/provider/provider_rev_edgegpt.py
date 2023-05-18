from model.provider.provider import Provider
from EdgeGPT import Chatbot, ConversationStyle
import json
import os
from util import general_utils as gu


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
        
    async def text_chat(self, prompt, platform = 'none'):
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
                if 'I\'m sorry but I prefer not to continue this conversation. I\'m still learning so I appreciate your understanding and patience.' in reply_msg:
                    self.busy = False
                    return '', 0
                if reply_msg == prompt:
                    # resp += '\n\n如果你没有让我复述你的话，那代表我可能不想和你继续这个话题了，请输入reset重置会话😶'
                    await self.forget()
                    err_count += 1
                    continue
                if reply_source is None:
                    # 不想答复
                    return '', 0
                else:
                    if platform != 'qqchan':
                        index = 1
                        if len(reply_source) > 0:
                            reply_msg += "\n\n信息来源:\n"
                        for i in reply_source:
                            reply_msg += f"[{str(index)}]: {i['seeMoreUrl']} | {i['providerDisplayName']}\n"
                            index += 1
                if throttling is not None:
                    if throttling['numUserMessagesInConversation'] == throttling['maxNumUserMessagesInConversation']:
                        # 达到上限，重置会话
                        await self.forget()
                    if throttling['numUserMessagesInConversation'] > throttling['maxNumUserMessagesInConversation']:
                        await self.forget()
                        err_count += 1
                        continue
                    reply_msg += f"\n⌈{throttling['numUserMessagesInConversation']}/{throttling['maxNumUserMessagesInConversation']}⌋"
                break
            except BaseException as e:
                gu.log(str(e), level=gu.LEVEL_WARNING, tag="RevEdgeGPT")
                err_count += 1
                if err_count >= retry_count:
                        gu.log(r"如果报错, 且您的机器在中国大陆内, 请确保您的电脑已经设置好代理软件(梯子), 并在配置文件设置了系统代理地址。详见https://github.com/Soulter/QQChannelChatGPT/wiki/%E4%BA%8C%E3%80%81%E9%A1%B9%E7%9B%AE%E9%85%8D%E7%BD%AE%E6%96%87%E4%BB%B6%E9%85%8D%E7%BD%AE", max_len=999)
                        self.busy = False
                        raise e
                gu.log("请求出现了一些问题, 正在重试。次数"+str(err_count), level=gu.LEVEL_WARNING, tag="RevEdgeGPT")
        self.busy = False
        
        # print("[RevEdgeGPT] "+str(reply_msg))
        return reply_msg, 1
    
