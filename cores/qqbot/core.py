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
        # 检测@头，返回对应session
        pattern0 = r"<@!\d+>"
        result0 = re.search(pattern0, message.content)
        if result0:
            session_id = result0.group(0)
            if session_id in session_dict:
                print("旧会话 "+session_id)
                chatgpt_res =await chatgpt.chat(session_dict[session_id]+' '+qq_msg)

                chatgpt_res = chatgpt_res.strip()
                session_dict[session_id] = session_dict[session_id] + ' ' + qq_msg 
                await message.reply(content=f"[ChatGPT]{chatgpt_res}")
            else:
                print("新会话 "+session_id)
                # new_session = chatgpt.newSession()
                session_dict[session_id] = qq_msg

                chatgpt_res = await chatgpt.chat(qq_msg)
                chatgpt_res = chatgpt_res.strip()
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