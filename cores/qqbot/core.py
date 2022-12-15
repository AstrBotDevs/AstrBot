import botpy
from botpy.message import Message
import yaml
import asyncio
import cores.openai.core
import re
from util.errors.errors import PromptExceededError
from botpy.message import DirectMessage
import json

chatgpt = ""
# db = ""
session_dict = {}
max_tokens = 2000
version = "1.3"
gpt_config = {
    'engine': '',
    'temperature': '',
    'top_p': '',
    'frequency_penalty': '',
    'presence_penalty': '',
    'max_tokens': '',
}
count = {
}
stat_file = ''
uniqueSession = False

class botClient(botpy.Client):
    async def on_at_message_create(self, message: Message):
        
        global stat_file
        try:
            if str(message.guild_id) not in count:
                count[str(message.guild_id)] = {
                    'count': 1,
                    'direct_count': 0,
                }
            else:
                count[str(message.guild_id)]['count'] += 1
            stat_file = open("./configs/stat", 'w', encoding='utf-8')
            stat_file.write(json.dumps(count))
            stat_file.flush()
            stat_file.close()
        except BaseException:
            pass

        await oper_msg(message=message, at=True)

    async def on_direct_message_create(self, message: DirectMessage):
        global stat_file
        try: 
            if str(message.guild_id) not in count:
                count[str(message.guild_id)] = {
                    'count': 1,
                    'direct_count': 1,
                }
            else:
                count[str(message.guild_id)]['count'] += 1
                count[str(message.guild_id)]['direct_count'] += 1
            stat_file = open("./configs/stat", 'w', encoding='utf-8')
            stat_file.write(json.dumps(count))
            stat_file.flush()
            stat_file.close()
        except BaseException:
            pass

        await oper_msg(message=message, at=False)

def initBot(chatgpt_inst):
    global chatgpt
    chatgpt = chatgpt_inst
    # global db
    # db = db_inst
    global max_tokens
    max_tokens = int(chatgpt_inst.getConfigs()['total_tokens_limit'])
    global gpt_config
    gpt_config = chatgpt_inst.getConfigs()
    gpt_config['key'] = "***"

    # 读统计信息
    global stat_file
    stat_file = open("./configs/stat", 'r', encoding='utf-8')
    global count
    res = stat_file.read()
    if res == '':
        count = {}
    else:
        try: 
            count = json.loads(res)
        except BaseException:
            pass

    global uniqueSession

    with open("./configs/config.yaml", 'r', encoding='utf-8') as ymlfile:
        cfg = yaml.safe_load(ymlfile)
        if cfg['qqbot']['uniqueSession'] == 'true':
            uniqueSession = True
        else:
            uniqueSession = False
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

def get_prompts_by_cache_list(cache_data_list, divide=False, paging=False, size=5, page=1):
    prompts = ""
    if paging:
        page_begin = (page-1)*size
        page_end = page*size
        if page_begin < 0:
            page_begin = 0
        if page_end > len(cache_data_list):
            page_end = len(cache_data_list)
        cache_data_list = cache_data_list[page_begin:page_end]
    for item in cache_data_list:
        prompts += str(item['prompt'])
        if divide:
            prompts += "----------\n"
    return prompts
    
def get_user_usage_tokens(cache_list):
    usage_tokens = 0
    for item in cache_list:
        usage_tokens += int(item['single_tokens'])
    return usage_tokens

async def oper_msg(message, at=False):
    print("[QQBOT] 接收到消息："+ message.content)
    qq_msg = ""

    if at:
        # 过滤用户id
        pattern = r"<@!\d+>\s+(.+)"
        # 多行匹配
        pattern = re.compile(pattern, flags=re.MULTILINE)
        result = re.search(pattern, message.content)
        if result:
            qq_msg = result.group(1).strip()
    else:
        qq_msg = message.content
    
    user_id = message.author.id
    if not at:
        session_id = message.author.id
    else:
        if uniqueSession:
            session_id = message.author.id
        else:
            session_id = message.guild_id
    if session_id:
        if qq_msg == "/reset":
            session_dict[session_id] = []
            if at:
                await message.reply(content=f"{message.member.nick}(id: {session_id}) 的历史记录重置成功")
            else:
                await message.reply(content=f"你的历史记录重置成功")
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
            if at:
                await message.reply(content=f"{message.member.nick} 的历史记录如下：\n{p}\n第{page}页 | 共{max_page}页\n*输入/his 2跳转到第2页")
            else:
                await message.reply(content=f"历史记录如下：\n{p}\n第{page}页 | 共{max_page}页\n*输入/his 2跳转到第2页")

            return
        if qq_msg == "/token":
            if at:
                await message.reply(content=f"{message.member.nick} 会话的token数: {get_user_usage_tokens(session_dict[session_id])}\n系统最大缓存token数: {max_tokens}")
            else:
                await message.reply(content=f"会话的token数: {get_user_usage_tokens(session_dict[session_id])}\n系统最大缓存token数: {max_tokens}")

            return
        if qq_msg == "/status":
            chatgpt_cfg_str = ""
            for k, v in gpt_config.items():
                if k == "key":
                    continue
                chatgpt_cfg_str += f"{k}: {v}"

            await message.reply(content=f"ChatGPT配置:\n - {chatgpt_cfg_str}\n QQChannelChatGPT 版本: {version}")
            return
        
        if qq_msg == "/count":
            try:
                f = open("./configs/stat", "r", encoding="utf-8")
                fjson = json.loads(f.read())
                f.close()
                guild_count = 0
                guild_msg_count = 0
                guild_direct_msg_count = 0

                for k,v in fjson.items():
                    guild_count += 1
                    guild_msg_count += v['count']
                    guild_direct_msg_count += v['direct_count']
                
                session_count = 0

                f = open("./configs/session", "r", encoding="utf-8")
                fjson = json.loads(f.read())
                f.close()
                for k,v in fjson.items():
                    session_count += 1
            except:
                pass

            await message.reply(content=f"当前会话数: {len(session_dict)}\n共有频道数: {guild_count} \n共有消息数: {guild_msg_count}\n私信数: {guild_direct_msg_count}\n历史会话数: {session_count}")
            return

        if qq_msg == "/help":
            await message.reply(content=f"请联系频道管理员或者前往github(仓库名: QQChannelChatGPT)提issue~")
            return
        
        if session_id not in session_dict:
            session_dict[session_id] = []

            fjson = {}
            try:
                f = open("./configs/session", "r", encoding="utf-8")
                fjson = json.loads(f.read())
                f.close()
            except:
                pass
            finally:
                fjson[session_id] = 'true'
                f = open("./configs/session", "w", encoding="utf-8")
                f.write(json.dumps(fjson))
                f.flush()
                f.close()


        # 获取缓存
        cache_prompt = ''
        cache_data_list = session_dict[session_id]
        cache_prompt = get_prompts_by_cache_list(cache_data_list)
        cache_prompt += "Human: "+ qq_msg + "\nAI: "
        # 请求chatGPT获得结果
        try:
            chatgpt_res, current_usage_tokens = await get_chatGPT_response(cache_prompt)
        except (PromptExceededError) as e:
            print("出现token超限, 清空对应缓存")
            # 超过4097tokens错误，清空缓存
            session_dict[session_id] = []
            cache_data_list = []
            cache_prompt = "Human: "+ qq_msg + "\nAI: "
            chatgpt_res, current_usage_tokens = await get_chatGPT_response(cache_prompt)
        except (BaseException) as e:
            print("OpenAI API错误:(")
            await message.reply(content=f"OpenAI API错误:( 原因如下：\n{str(e)} \n*前往github(仓库名: QQChannelChatGPT)反馈~")

        # 超过指定tokens， 尽可能的保留最多的条目，直到小于max_tokens
        # print("current_usage_tokens: ", current_usage_tokens)
        # print("max_tokens: ", max_tokens)
        if current_usage_tokens > max_tokens:
            t = current_usage_tokens
            cache_list = session_dict[session_id]
            index = 0
            while t > max_tokens:
                if index >= len(cache_list):
                    break
                t -= int(cache_list[index]['single_tokens'])
                index += 1
            session_dict[session_id] = cache_list[index:]
            cache_data_list = session_dict[session_id]
            cache_prompt = get_prompts_by_cache_list(cache_data_list)

        # cache_prompt += chatgpt_res + "\n";
        # 添加新条目进入缓存的prompt
        if len(cache_data_list) > 0: 
            single_record = {
                "prompt": f'Human: {qq_msg}\nAI: {chatgpt_res}\n',
                "usage_tokens": current_usage_tokens,
                "single_tokens": current_usage_tokens - int(cache_data_list[-1]['usage_tokens'])
            }
        else:
            single_record = {
                "prompt": f'Human: {qq_msg}\nAI: {chatgpt_res}\n',
                "usage_tokens": current_usage_tokens,
                "single_tokens": current_usage_tokens
            }
        # print(single_record)
        cache_data_list.append(single_record)

        # 写入数据库
        # try:
        #     data = {
        #         "data": cache_data_list
        #     }
        #     data_str = json.dumps(data)
        #     if len(cache_data_list) > 1:
        #         db.update_session(session_id, data_str)
        #     else:
        #         db.insert_session(session_id, data_str)
        # except Exception as e:
        #     print(e)
        #     print("数据库写入失败")
        
        session_dict[session_id] = cache_data_list

        # #检测是否存在url，如果存在，则去除url 防止被qq频道过滤
        chatgpt_res = chatgpt_res.replace(".", " . ")

        # 发送qq信息
        try:
            await message.reply(content=f"[ChatGPT]{chatgpt_res}")
        except BaseException as e:
            print("QQ频道API错误: \n"+str(e))
            f_res = ""
            for t in chatgpt_res:
                f_res += t + ' '
            await message.reply(content=f"QQ频道API错误：{str(e)}\n下面是格式化后的回答：\n{f_res}")