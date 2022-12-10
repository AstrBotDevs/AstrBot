import botpy
from botpy.message import Message
import yaml
import asyncio
import cores.openai.core
import re
from util.errors.errors import PromptExceededError
from botpy.message import DirectMessage

chatgpt = ""
session_dict = {}
max_tokens = 2000

class botClient(botpy.Client):
    async def on_at_message_create(self, message: Message):
        await oper_msg(message=message)

    async def on_direct_message_create(self, message: DirectMessage):
        print(message.content)
        await oper_msg(message=message)

def initBot(chatgpt_inst):
    global chatgpt
    chatgpt = chatgpt_inst
    global max_tokens
    max_tokens = int(chatgpt_inst.getConfigs()['total_tokens_limit'])
    with open("./configs/config.yaml", 'r', encoding='utf-8') as ymlfile:
        cfg = yaml.safe_load(ymlfile)
        if cfg['qqbot']['appid'] != '' or cfg['qqbot']['token'] != '':
            print("读取QQBot appid token 成功")
            intents = botpy.Intents(public_guild_messages=True, direct_message=True) 
            client = botClient(intents=intents)
            client.run(appid=cfg['qqbot']['appid'], token=cfg['qqbot']['token'])
        else:
            raise BaseException("请在config中完善你的appid和token")


async def get_chatGPT_response(prompts_str):
    res = ''
    usage = ''
    res, usage = await chatgpt.chat(prompts_str)
    # 处理结果文本
    chatgpt_res = res.strip()
    return res, usage

def get_prompts_by_cache_list(cache_prompt_list, divide=False, paging=False, size=5, page=1):
    prompts = ""
    if paging:
        page_begin = (page-1)*size
        page_end = page*size
        if page_begin < 0:
            page_begin = 0
        if page_end > len(cache_prompt_list):
            page_end = len(cache_prompt_list)
        cache_prompt_list = cache_prompt_list[page_begin:page_end]
    for item in cache_prompt_list:
        prompts += str(item['prompt'])
        if divide:
            prompts += "----------\n"
    return prompts
    
def get_user_usage_tokens(cache_list):
    usage_tokens = 0
    for item in cache_list:
        usage_tokens += int(item['single_tokens'])
    return usage_tokens

async def oper_msg(message):
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
    # session_id_pattern = r"<@!\d+>"
    # session_id_result = re.search(session_id_pattern, message.content)
    session_id = message.author.id
    if session_id:
        if qq_msg == "/reset":
            session_dict[session_id] = []
            await message.reply(content=f"{message.member.nick}(id: {session_id}) 的历史记录重置成功")
            return
        if qq_msg[:4] == "/his":

            #分页，每页5条
            size_per_page = 3
            page = 1
            if qq_msg[5:]:
                page = int(qq_msg[5:])
            l = session_dict[session_id]
            max_page = len(l)//size_per_page + 1 if len(l)%size_per_page != 0 else len(l)//size_per_page
            p = get_prompts_by_cache_list(session_dict[session_id], divide=True, paging=True, size=size_per_page, page=page)
            await message.reply(content=f"{message.member.nick} 的历史记录如下：\n{p}\n第{page}页 | 共{max_page}页")
            return
        if qq_msg == "/token":
            await message.reply(content=f"{message.member.nick} 会话的token数: {get_user_usage_tokens(session_dict[session_id])}\n系统最大缓存token数: {max_tokens}")
            return

        if session_id not in session_dict:
            session_dict[session_id] = []

        # 获取缓存
        cache_prompt = ''
        cache_prompt_list = session_dict[session_id]
        cache_prompt = get_prompts_by_cache_list(cache_prompt_list)
        cache_prompt += "Human: "+ qq_msg + "\nAI: "
        # 请求chatGPT获得结果
        try:
            chatgpt_res, current_usage_tokens = await get_chatGPT_response(cache_prompt)
        except (PromptExceededError) as e:
            print(e)
            
            # 超过4097tokens错误，清空缓存
            session_dict[session_id] = []
            cache_prompt_list = []
            cache_prompt = "Human: "+ qq_msg + "\nAI: "
            chatgpt_res, current_usage_tokens = await get_chatGPT_response(cache_prompt)

        # 超过指定tokens， 尽可能的保留最多的条目，直到小于max_tokens
        # print("current_usage_tokens: ", current_usage_tokens)
        # print("max_tokens: ", max_tokens)
        if current_usage_tokens > max_tokens:
            t = current_usage_tokens
            cache_list = session_dict[session_id]
            index = 0
            while t > max_tokens:
                t -= int(cache_list[index]['single_tokens'])
                index += 1
            session_dict[session_id] = cache_list[index:]
            cache_prompt_list = session_dict[session_id]
            cache_prompt = get_prompts_by_cache_list(cache_prompt_list)

        # cache_prompt += chatgpt_res + "\n";
        # 添加新条目进入缓存的prompt
        if len(cache_prompt_list) > 0: 
            single_record = {
                "prompt": f'Human: {qq_msg}\nAI: {chatgpt_res}\n',
                "usage_tokens": current_usage_tokens,
                "single_tokens": current_usage_tokens - int(cache_prompt_list[-1]['usage_tokens'])
            }
        else:
            single_record = {
                "prompt": f'Human: {qq_msg}\nAI: {chatgpt_res}\n',
                "usage_tokens": current_usage_tokens,
                "single_tokens": current_usage_tokens
            }
        # print(single_record)
        cache_prompt_list.append(single_record)
        session_dict[session_id] = cache_prompt_list

        # #检测是否存在url，如果存在，则去除url 防止被qq频道过滤
        chatgpt_res = chatgpt_res.replace(".", " . ")

        # 发送qq信息
        await message.reply(content=f"[ChatGPT]{chatgpt_res}")