import botpy
from botpy.message import Message
import yaml
import asyncio
import cores.openai.core
import re
from util.errors.errors import PromptExceededError

chatgpt = ""

session_dict = {}

class botClient(botpy.Client):
    async def on_at_message_create(self, message: Message):
        print("[QQBOT] 接收到消息："+ message.content)
        qq_msg = ""
        # 过滤用户id
        pattern = r"<@!\d+>\s+(.+)"
        # 多行匹配
        pattern = re.compile(pattern, flags=re.MULTILINE)
        result = re.search(pattern, message.content)
        if result:
            qq_msg = result.group(1).strip()

        # 检测用户id，返回对应缓存的prompt
        session_id_pattern = r"<@!\d+>"
        session_id_result = re.search(session_id_pattern, message.content)
        if session_id_result:
            # 匹配出sessionid
            session_id = session_id_result.group(0)

            if qq_msg == "/reset":
                session_id = session_id_result.group(0)
                session_dict[session_id] = []
                await message.reply(content=f"{message.member.nick} 的历史记录重置成功")
                return
            if qq_msg == "/his":
                p = getPromptsByCacheList(session_dict[session_id], divide=True)
                await message.reply(content=f"{message.member.nick} 的历史记录如下：\n{p}")
                return

            if session_id not in session_dict:
                session_dict[session_id] = []

            # 获取缓存
            cache_prompt = ''
            cache_prompt_list = session_dict[session_id]
            cache_prompt = getPromptsByCacheList(cache_prompt_list)
            cache_prompt += "Human: "+ qq_msg + "\nAI: "
            # 请求chatGPT获得结果
            try:
                chatgpt_res = await getChatGPTResponse(cache_prompt)
            except (PromptExceededError) as e:
                print(e)
                
                # 超过了4096个tokens，清空cache
                session_dict[session_id] = []
                cache_prompt_list = []
                cache_prompt = "Human: "+ qq_msg + "\nAI: "
                chatgpt_res = await getChatGPTResponse(cache_prompt)
                

            # 处理结果文本
            chatgpt_res = chatgpt_res.strip()

            cache_prompt += chatgpt_res + "\n";
            # 添加新条目进入缓存的prompt
            cache_prompt_list.append(f'Human: {qq_msg}\nAI: {chatgpt_res}\n')
            session_dict[session_id] = cache_prompt_list

            # #检测是否存在url，如果存在，则去除url 防止被qq频道过滤
            # chatgpt_res = re.sub(r"([\s]+)(http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+)([\s]+)", r"\1\3", chatgpt_res)
            chatgpt_res = chatgpt_res.replace(".", " . ")

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

async def getChatGPTResponse(prompts_str):
    return await chatgpt.chat(prompts_str)

def getPromptsByCacheList(cache_prompt_list, divide=False):
    prompts = ""
    for item in cache_prompt_list:
        prompts += str(item)
        if divide:
            prompts += "----------\n"
    return prompts
    