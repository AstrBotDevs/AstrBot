import botpy
from botpy.message import Message
import yaml
import re
from util.errors.errors import PromptExceededError
from botpy.message import DirectMessage
import json
# from concurrent.futures import ThreadPoolExecutor
import threading
import asyncio
import time
from cores.database.conn import dbConn

history_dump_interval = 10
client = ''
# executor = ThreadPoolExecutor(max_workers=10)
# ChatGPT的实例
chatgpt = ""
# 缓存的会话
session_dict = {}
# 最大缓存token（在配置里改 configs/config.yaml）
max_tokens = 2000
# 版本
version = "1.4"
# gpt配置（在配置改）
gpt_config = {
    'engine': '',
    'temperature': '',
    'top_p': '',
    'frequency_penalty': '',
    'presence_penalty': '',
    'max_tokens': '',
}
# 统计信息
count = {
}
# 统计信息
stat_file = ''
# 是否是独立会话（在配置改）
uniqueSession = False

def new_sub_thread(func, args=()):
    thread = threading.Thread(target=func, args=args, daemon=True)
    thread.start()

class botClient(botpy.Client):
    # 收到At消息
    async def on_at_message_create(self, message: Message):
        toggle_count(at=True, message=message)
        # executor.submit(oper_msg, message, True)
        new_sub_thread(oper_msg, (message, True))
        # await oper_msg(message=message, at=True)

    # 收到私聊消息
    async def on_direct_message_create(self, message: DirectMessage):
        toggle_count(at=False, message=message)
        # executor.submit(oper_msg, message, True)
        # await oper_msg(message=message, at=False)
        new_sub_thread(oper_msg, (message, False))

# 写入统计信息
def toggle_count(at: bool, message):
    global stat_file
    try: 
        if str(message.guild_id) not in count:
            count[str(message.guild_id)] = {
                'count': 1,
                'direct_count': 1,
            }
        else:
            count[str(message.guild_id)]['count'] += 1
            if not at:
                count[str(message.guild_id)]['direct_count'] += 1
        stat_file = open("./configs/stat", 'w', encoding='utf-8')
        stat_file.write(json.dumps(count))
        stat_file.flush()
        stat_file.close()
    except BaseException:
        pass

# 转储历史记录的定时器~ Soulter
def dump_history():
    time.sleep(10)
    global session_dict, history_dump_interval
    db = dbConn()
    while True:
        try:
            # print("转储历史记录...")
            for key in session_dict:
                # print("TEST: "+str(db.get_session(key)))
                data = session_dict[key]
                data_json = {
                    'data': data
                }
                if db.check_session(key):
                    db.update_session(key, json.dumps(data_json))
                else:
                    db.insert_session(key, json.dumps(data_json))
            # print("转储历史记录完毕")
        except BaseException as e:
            print(e)
        # 每隔10分钟转储一次
        time.sleep(10*history_dump_interval)

def initBot(chatgpt_inst):
    global chatgpt
    chatgpt = chatgpt_inst

    global max_tokens
    max_tokens = int(chatgpt_inst.getConfigs()['total_tokens_limit'])
    global gpt_config
    gpt_config = chatgpt_inst.getConfigs()
    gpt_config['key'] = "***"
    global version

    # 读取历史记录 Soulter
    try:
        db1 = dbConn()
        for session in db1.get_all_session():
            session_dict[session[0]] = json.loads(session[1])['data']
        print("历史记录读取成功了喵")
    except BaseException as e:
        print("历史记录读取失败: " + str(e))

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

    # 创建转储定时器线程
    threading.Thread(target=dump_history, daemon=True).start()

    global uniqueSession, history_dump_interval
    with open("./configs/config.yaml", 'r', encoding='utf-8') as ymlfile:
        cfg = yaml.safe_load(ymlfile)

        try:
            if 'uniqueSessionMode' in cfg and cfg['qqbot']['uniqueSessionMode'] == 'true':
                uniqueSession = True
            else:
                uniqueSession = False
            print("独立会话模式为" + str(uniqueSession))
            if 'version' in cfg:
                version = cfg['version']
                print("当前版本为" + str(version))
            if 'dump_history_interval' in cfg:
                history_dump_interval = int(cfg['dump_history_interval'])
                print("历史记录转储间隔为" + str(history_dump_interval) + "分钟")
        except BaseException:
            print("读取uniqueSessionMode/version/dump_history_interval配置文件失败, 使用默认值喵~")

        if cfg['qqbot']['appid'] != '' or cfg['qqbot']['token'] != '':
            print("读取QQBot appid,token 成功")
            intents = botpy.Intents(public_guild_messages=True, direct_message=True) 
            global client
            client = botClient(intents=intents)
            client.run(appid=cfg['qqbot']['appid'], token=cfg['qqbot']['token'])
        else:
            raise BaseException("请在config中完善你的appid和token")

'''
得到OpenAI的回复
'''
def get_chatGPT_response(prompts_str):
    res = ''
    usage = ''
    res, usage = chatgpt.chat(prompts_str)
    # 处理结果文本
    chatgpt_res = res.strip()
    return res, usage

'''
回复QQ消息
'''
def send_qq_msg(message, res):
    asyncio.run_coroutine_threadsafe(message.reply(content=res), client.loop)

'''
获取缓存的会话
'''
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

def oper_msg(message, at=False, loop=None):
    print("[QQBOT] 接收到消息："+ message.content)
    qq_msg = ''
    session_id = ''
    name = ''

    if at:
        # 过滤用户id
        pattern = r"<@!\d+>\s+(.+)"
        # 多行匹配
        pattern = re.compile(pattern, flags=re.MULTILINE)
        result = re.search(pattern, message.content)
        if result:
            qq_msg = result.group(1).strip()
        if uniqueSession:
            session_id = message.author.id
        else:
            session_id = message.guild_id
    else:
        qq_msg = message.content
        session_id = message.author.id
        
    if uniqueSession:
        name = message.member.nick
    else:
        name = "频道"

    # 指令控制
    if qq_msg == "/reset":
        msg = ''
        session_dict[session_id] = []
        if at:
            msg = f"{name}(id: {session_id}) 的历史记录重置成功"
        else:
            msg = f"你的历史记录重置成功"
        send_qq_msg(message, msg)
        return
    if qq_msg[:4] == "/his":
        #分页，每页5条
        msg = ''
        size_per_page = 3
        page = 1
        if qq_msg[5:]:
            page = int(qq_msg[5:])
        # 检查是否有过历史记录
        if session_id not in session_dict:
            msg = f"{name} 的历史记录为空"
        l = session_dict[session_id]
        max_page = len(l)//size_per_page + 1 if len(l)%size_per_page != 0 else len(l)//size_per_page
        p = get_prompts_by_cache_list(session_dict[session_id], divide=True, paging=True, size=size_per_page, page=page)
        if at:
            msg=f"{name} 的历史记录如下：\n{p}\n第{page}页 | 共{max_page}页\n*输入/his 2跳转到第2页"
        else:
            msg=f"历史记录如下：\n{p}\n第{page}页 | 共{max_page}页\n*输入/his 2跳转到第2页"
        send_qq_msg(message, msg)
        return
    if qq_msg == "/token":
        msg = ''
        if at:
            msg=f"{name} 会话的token数: {get_user_usage_tokens(session_dict[session_id])}\n系统最大缓存token数: {max_tokens}"
        else:
            msg=f"会话的token数: {get_user_usage_tokens(session_dict[session_id])}\n系统最大缓存token数: {max_tokens}"
        send_qq_msg(message, msg)
        return
    if qq_msg == "/status":
        chatgpt_cfg_str = ""
        for k, v in gpt_config.items():
            if k == "key":
                continue
            chatgpt_cfg_str += f"{k}: {v}"
        
        key_stat = chatgpt.get_key_stat()
        key_list = chatgpt.get_key_list()
        chatgpt_cfg_str += '\n\n配额使用情况:\n'
        index = 1
        max = 900000
        for key in key_list:
            if key in key_stat:
                if key_stat[key]['exceed']:
                    chatgpt_cfg_str += f"#{index}: 已寄\n"
                    index += 1
                    continue
                # chatgpt_cfg_str += f"#{index}: {round(key_stat[key]['used']/max*100, 2)}%\n"
                chatgpt_cfg_str += f"#{index}: {key_stat[key]['used']}/{max}\n"
                index += 1
        chatgpt_cfg_str += '\n注: 配额情况在某些极端情况下具有一定的不准确性。\n'
        print("生成...")
        send_qq_msg(message, f"ChatGPT配置:\n {chatgpt_cfg_str}\n QQChannelChatGPT 版本: {version}")
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
        send_qq_msg(message, f"当前会话数: {len(session_dict)}\n共有频道数: {guild_count} \n共有消息数: {guild_msg_count}\n私信数: {guild_direct_msg_count}\n历史会话数: {session_count}")
        return
    if qq_msg == "/help":
        send_qq_msg(message, "请联系频道管理员或者前往github(仓库名: QQChannelChatGPT)提issue~")
        return
    
    # 统计历史会话
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
        chatgpt_res, current_usage_tokens = get_chatGPT_response(cache_prompt)
    except (PromptExceededError) as e:
        print("出现token超限, 清空对应缓存")
        # 超过4097tokens错误，清空缓存
        session_dict[session_id] = []
        cache_data_list = []
        cache_prompt = "Human: "+ qq_msg + "\nAI: "
        chatgpt_res, current_usage_tokens = get_chatGPT_response(cache_prompt)
    except (BaseException) as e:
        print("OpenAI API错误:(")
        send_qq_msg(message, f"OpenAI API错误:( 原因如下：\n{str(e)} \n*前往github(仓库名: QQChannelChatGPT)反馈~")
        return

    # 发送qq信息
    try:
        # 防止被qq频道过滤消息
        gap_chatgpt_res = chatgpt_res.replace(".", " . ")
        # 发送信息
        send_qq_msg(message, '[ChatGPT]'+gap_chatgpt_res)
    except BaseException as e:
        print("QQ频道API错误: \n"+str(e))
        f_res = ""
        for t in chatgpt_res:
            f_res += t + ' '
        try:
            pass
            # send(message, f"QQ频道API错误：{str(e)}\n下面是格式化后的回答：\n{f_res}")
        except BaseException as e:
            # 如果还是不行则过滤url
            f_res = re.sub(r'(https|http)?:\/\/(\w|\.|\/|\?|\=|\&|\%)*\b', '', f_res, flags=re.MULTILINE)
            f_res = f_res.replace(".", " . ")
            # send(message, f"QQ频道API错误：{str(e)}\n下面是格式化后的回答：\n{f_res}")

    # 超过指定tokens， 尽可能的保留最多的条目，直到小于max_tokens
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
    cache_data_list.append(single_record)
    session_dict[session_id] = cache_data_list