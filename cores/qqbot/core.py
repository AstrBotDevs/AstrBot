import botpy
from botpy.message import Message
import yaml
import asyncio
import cores.openai.core
import re

chatgpt = ""

session_dict = {}

class botClient(botpy.Client):
    async def on_at_message_create(self, message: Message):
        print(message.content)
        qq_msg = ""
        # 过滤@头
        pattern = r"<@!\d+>\s+(.+)"
        result = re.search(pattern, message.content)
        if result:
            qq_msg = result.group(1).strip()
        print(qq_msg)
        # 检测@头，返回对应缓存的prompt
        session_id_pattern = r"<@!\d+>"
        session_id_result = re.search(session_id_pattern, message.content)
        if session_id_result:
            # 匹配出sessionid
            session_id = session_id_result.group(0)
            # 添加新条目进入缓存的prompt
            session_dict[session_id] = "Human: "+ qq_msg + "\nAI: "
            # 请求chatGPT获得结果
            chatgpt_res = await chatgpt.chat(session_dict[session_id])
            # 处理结果文本
            chatgpt_res = chatgpt_res.strip()
            session_dict[session_id] += chatgpt_res + "\n"
            print(f'{session_id} 目前prompt: {session_dict[session_id]}' )
            # 发送qq信息
            await message.reply(content=f"[ChatGPT]{chatgpt_res}")

def initBot(chatgpt_inst):
    global chatgpt
    chatgpt = chatgpt_inst
    with open("./configs/config.yaml", 'r', encoding='utf-8') as ymlfile:
        cfg = yaml.safe_load(ymlfile)
        if cfg['qqbot']['appid'] != '' or cfg['qqbot']['token'] != '':
            print("读取QQBot appid token 成功")
            intents = botpy.Intents(public_guild_messages=True) 
            client = botClient(intents=intents)
            client.run(appid=cfg['qqbot']['appid'], token=cfg['qqbot']['token'])
        else:
            raise BaseException("请在config中完善你的appid和token")