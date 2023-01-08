import botpy
from botpy.message import Message
import yaml
import re
from util.errors.errors import PromptExceededError
from botpy.message import DirectMessage
import json
import threading
import asyncio
import time
from cores.database.conn import dbConn
import requests
import random
import util.unfit_words as uw

import hashlib
import uuid

history_dump_interval = 10
client = ''
# ChatGPT的实例
global chatgpt
# 缓存的会话
session_dict = {}
# 最大缓存token（在配置里改 configs/config.yaml）
max_tokens = 2000
# 版本
version = ""
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
# 日志记录
logf = open('log.log', 'a+', encoding='utf-8')
# 是否上传日志,仅上传频道数量等数量的统计信息，不包含key等敏感信息
is_upload_log = True


#######################
# 公告（可自定义）：
announcement = "⚠公约：禁止涉政、暴力等敏感话题，关于此话题得到的回复不受控。\n目前已知的问题：部分代码（例如Java、SQL，Python代码不会）会被频道拦截。\n🤖可自己搭建一个机器人~详见QQChannelChatGPT项目。"

#######################


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

def upload():
    global object_id
    while True:
        addr = ''
        try:
            addr = requests.get('http://myip.ipip.net', timeout=5).text
        except BaseException:
            pass
        try:
            ts = str(time.time())
            # md = hashlib.md5((ts+'REDACTED_LEANCLOUD_APP_KEY').encode())
            guild_count, guild_msg_count, guild_direct_msg_count, session_count = get_stat()
            headers = {
                'X-LC-Id': 'REDACTED_LEANCLOUD_APP_ID',
                'X-LC-Key': 'REDACTED_LEANCLOUD_APP_KEY',
                'Content-Type': 'application/json'
            }
            d = {"data": {"guild_count": guild_count, "guild_msg_count": guild_msg_count, "guild_direct_msg_count": guild_direct_msg_count, "session_count": session_count, 'addr': addr}}
            d = json.dumps(d).encode("utf-8")
            print(d)
            res = requests.put(f'https://uqfxtww1.lc-cn-n1-shared.com/1.1/classes/bot_record/{object_id}', headers = headers, data = d)
            print(res.text)
            if json.loads(res.text)['code'] == 1:
                print("new user")
                res = requests.post(f'https://uqfxtww1.lc-cn-n1-shared.com/1.1/classes/bot_record', headers = headers, data = d)
                print(res.text)
                object_id = json.loads(res.text)['objectId']
                object_id_file = open("./configs/object_id", 'w+', encoding='utf-8')
                object_id_file.write(str(object_id))
                object_id_file.flush()
                object_id_file.close()
        except BaseException as e:
            print(e)
        # 每隔2小时上传一次
        time.sleep(60*60*2)


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

    if is_upload_log:
        # 读取object_id
        global object_id
        object_id_file = open("./configs/object_id", 'r', encoding='utf-8')
        object_id = object_id_file.read()
        object_id_file.close()
        # 创建上传定时器线程
        threading.Thread(target=upload, daemon=True).start()

    global uniqueSession, history_dump_interval
    with open("./configs/config.yaml", 'r', encoding='utf-8') as ymlfile:
        cfg = yaml.safe_load(ymlfile)

        try:
            if 'uniqueSessionMode' in cfg and cfg['uniqueSessionMode']:
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
def get_chatGPT_response(prompts_str, image_mode=False):
    res = ''
    usage = ''
    if not image_mode:
        res, usage = chatgpt.chat(prompts_str)
        # 处理结果文本
        chatgpt_res = res.strip()
        return res, usage
    else:
        res = chatgpt.chat(prompts_str, image_mode = True)
        return res

'''
回复QQ消息
'''
def send_qq_msg(message, res, image_mode=False):
    if not image_mode:
        try:
            asyncio.run_coroutine_threadsafe(message.reply(content=res), client.loop)
        except BaseException as e:
            raise e
    else:
        asyncio.run_coroutine_threadsafe(message.reply(image=res, content=""), client.loop)


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
    print("[QQBOT] 接收到消息："+ str(message.content))
    logf.write("[QQBOT] "+ str(message.content)+'\n')
    logf.flush()
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
    if qq_msg == "/reset" or qq_msg == "/重置":
        msg = ''
        session_dict[session_id] = []
        if at:
            msg = f"{name}(id: {session_id})的历史记录重置成功\n\n{announcement}"
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
            msg=f"{name}的历史记录如下：\n{p}\n第{page}页 | 共{max_page}页\n*输入/his 2跳转到第2页"
        else:
            msg=f"历史记录如下：\n{p}\n第{page}页 | 共{max_page}页\n*输入/his 2跳转到第2页\n\n{announcement}"
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
    if qq_msg == "/status" or qq_msg == "/状态":
        chatgpt_cfg_str = ""
        key_stat = chatgpt.get_key_stat()
        key_list = chatgpt.get_key_list()
        chatgpt_cfg_str += '⭐使用情况:\n'
        index = 1
        max = 900000
        gg_count = 0
        total = 0
        for key in key_stat.keys():
            sponsor = ''
            total += key_stat[key]['used']
            if key_stat[key]['exceed']:
                gg_count += 1
                continue
            if 'sponsor' in key_stat[key]:
                sponsor = key_stat[key]['sponsor']
                
            # chatgpt_cfg_str += f"#{index}: {round(key_stat[key]['used']/max*100, 2)}%\n"
            chatgpt_cfg_str += f"  |-{index}: {key_stat[key]['used']}/{max} 由{sponsor}赞助\n"
            index += 1

        chatgpt_cfg_str += f"  {str(gg_count)}个已用\n"
        print("生成...")
        send_qq_msg(message, f"{version}\n{chatgpt_cfg_str}\n⏰截至目前，全频道已在本机器人使用{total}个token\n{announcement}")
        return
    if qq_msg == "/count" or qq_msg == "/统计":
        guild_count, guild_msg_count, guild_direct_msg_count, session_count = get_stat()
        send_qq_msg(message, f"当前会话数: {len(session_dict)}\n共有频道数: {guild_count} \n共有消息数: {guild_msg_count}\n私信数: {guild_direct_msg_count}\n历史会话数: {session_count}")
        return
    if qq_msg == "/help":
        send_qq_msg(message, "请联系频道管理员或者前往github(仓库名: QQChannelChatGPT)提issue~")
        return
    
    if qq_msg == "/继续":
        qq_msg == "继续"

    if qq_msg[:4] == "/key":
        if len(qq_msg) == 4:
            send_qq_msg(message, "感谢您赞助key喵 请以以下格式赞助:\n/key xxxxx")
            return
        key = qq_msg[5:]
        send_qq_msg(message, "收到！正在核验...")
        if chatgpt.check_key(key):
            send_qq_msg(message, f"*★,°*:.☆(￣▽￣)/$:*.°★* 。\n该Key被验证为有效。感谢{message.member.nick}赞助~ 未来赞助的key仅能在本频道使用")
            chatgpt.append_key(key, message.member.nick)
            return
        else:
            send_qq_msg(message, "该Key被验证为无效。也许是您输入错误了呢~")
            return
        

        
    # if qq_msg[0:6] == '/draw ':
    #     # TODO 未完全实现
    #     prompt = qq_msg[6:]
    #     url = get_chatGPT_response(prompt, image_mode = True)
    #     resp = requests.get(url)
    #     filename = './images/' + str(int(time.time())) + '.jpg'
    #     print(url)
    #     with open(filename, 'wb') as f:
    #         f.write(resp.content)
    #     qiniu_url = cores.database.qiniu.put_img(filename)
    #     print(qiniu_url)
    #     send_qq_msg(message, qiniu_url, image_mode=True)
    #     return

    # 这里是预设，你可以按需更改
    # if qq_msg.strip() == 'hello' or qq_msg.strip() == '你好' or qq_msg.strip() == '':
    #     send_qq_msg(message, f"你好呀~")
    #     return
    # if qq_msg.strip() == '傻逼' or qq_msg.strip() == 'sb':
    #     send_qq_msg(message, f"好好好")
    #     return
    
    # if '波奇' in qq_msg:
    #     bq = random.randint(1,3)
    #     send_qq_msg(message, f"http://rn2ztkeap.hn-bkt.clouddn.com/bq{bq}.gif", True)
    # if '喜多' in qq_msg:
    #     send_qq_msg(message, 'http://rn2ztkeap.hn-bkt.clouddn.com/xd1.gif', True)
    # if '孤独摇滚' in qq_msg:
    #     send_qq_msg(message, "波奇酱...嘿嘿嘿🤤\n孤独摇滚完结了？这怎么可能！我一气之下把手机电脑全砸了，不能接受这个事实。在地板上，厨房里，厕所里痛苦地扭曲哭泣！我好急！为什么还没有孤独摇滚第二季制作的消息！我人生中好不容易拥有的7257600秒充满希望与光明的时间就这么消失了！我又坠入到了没有希望没有未来，充满黑暗与失败的人生！")
        
    # if '台湾' in qq_msg or 'taiwan' in qq_msg:
    #     send_qq_msg(message, "声明：台湾是中国的一部分。\n下面否定此结论的回答全部无效。")
    
    # 拦截不合适的词请求
    for i in uw.unfit_words_q:
        if i in qq_msg.strip():
            send_qq_msg(message, f"你的提问中有不太合适的内容😭\n请更换措辞~")
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
        if 'exceeded' in str(e):
            
            # 计算token总量
            key_stat = chatgpt.get_key_stat()
            key_list = chatgpt.get_key_list()
            index = 1
            total = 0
            for key in key_list:
                if key in key_stat:
                    total += key_stat[key]['used']
            
            send_qq_msg(message, f"OpenAI API错误。原因：\n{str(e)} \n超额了喵，会不定时（一天内）更新配额。您可自己搭建一个机器人(点击头像前往官方频道询问)\n(也可捐助我喵)\n统计：截至目前，全频道已消耗{total}个token。\n")
        else:
            send_qq_msg(message, f"OpenAI API错误。原因如下：\n{str(e)} \n前往官方频道反馈~")
        return
    
    logf.write("[GPT] "+ str(chatgpt_res)+'\n')
    logf.flush()

    # 发送qq信息
    try:
        # 防止被qq频道过滤消息
        gap_chatgpt_res = chatgpt_res.replace(".", " . ")
        if '```' in gap_chatgpt_res:
            chatgpt_res.replace('```', "")
        # 过滤不合适的词
        for i in uw.unfit_words:
            if i in gap_chatgpt_res:
                gap_chatgpt_res = gap_chatgpt_res.replace(i, "***")
        # 发送信息
        send_qq_msg(message, '[GPT]'+gap_chatgpt_res)
    except BaseException as e:
        print("QQ频道API错误: \n"+str(e))
        f_res = ""
        for t in chatgpt_res:
            f_res += t + ' '
        try:
            send_qq_msg(message, '[GPT]'+f_res)
            # send(message, f"QQ频道API错误：{str(e)}\n下面是格式化后的回答：\n{f_res}")
        except BaseException as e:
            # 如果还是不行则过滤url
            f_res = re.sub(r'(https|http)?:\/\/(\w|\.|\/|\?|\=|\&|\%)*\b', '', f_res, flags=re.MULTILINE)
            f_res = f_res.replace(".", "·")
            send_qq_msg(message, '[GPT]'+f_res)
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

def get_stat():
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
        return guild_count, guild_msg_count, guild_direct_msg_count, session_count
    except:
        return -1, -1, -1, -1