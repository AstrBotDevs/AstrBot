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
        try:
            print("[QQBOT] 接收到消息："+ message.content)
            qq_msg = ""
            # 过滤@头
            pattern = r"<@!\d+>\s+(.+)"
            result = re.search(pattern, message.content)
            if result:
                qq_msg = result.group(1).strip()

            # 检测@头，返回对应缓存的prompt
            session_id_pattern = r"<@!\d+>"
            session_id_result = re.search(session_id_pattern, message.content)
            if session_id_result:
                # 匹配出sessionid
                session_id = session_id_result.group(0)

                if qq_msg == "/reset":
                    session_id = session_id_result.group(0)
                    session_dict[session_id] = ""
                    await message.reply(content=f"{message.member.nick} [ChatGPT] 重置成功")
                    return

                if session_id not in session_dict:
                    session_dict[session_id] = ""
                # 添加新条目进入缓存的prompt
                session_dict[session_id] += "Human: "+ qq_msg + "\nAI: "
                # 请求chatGPT获得结果
                chatgpt_res = await chatgpt.chat(session_dict[session_id])
                # 处理结果文本
                chatgpt_res = chatgpt_res.strip()

                session_dict[session_id] += chatgpt_res + "\n"

                #检测是否存在url，如果存在，则去除url 防止被qq过滤
                chatgpt_res = re.sub(r"([\s]+)(http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+)([\s]+)", r"\1\3", chatgpt_res)

                print(f'{session_id} 目前prompt: {session_dict[session_id]}' )
                # 发送qq信息
                await message.reply(content=f"[ChatGPT]{chatgpt_res}")
        except botpy.errors.Forbidden:
            print("无法发送消息，可能是因为没有给botpy发消息的权限")

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