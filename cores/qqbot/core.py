import botpy
from botpy.message import Message
from botpy.types.message import Reference
import re
from botpy.message import DirectMessage
import json
import threading
import asyncio
import time
import requests
import util.unfit_words as uw
import os
import sys
from cores.qqbot.personality import personalities
from addons.baidu_aip_judge import BaiduJudge
from model.platform.qqchan import QQChan
from model.platform.qq import QQ
from nakuru import (
    CQHTTP,
    GroupMessage,
    GroupMemberIncrease,
    FriendMessage
)
from nakuru.entities.components import Plain,At

# QQBotClient实例
client = ''
# ChatGPT实例
global chatgpt
# 缓存的会话
session_dict = {}
# 最大缓存token（在配置里改 configs/config.yaml）
max_tokens = 2000
# 配置信息
config = {}
# 统计信息
count = {}
# 统计信息
stat_file = ''
# 是否独立会话默认值
uniqueSession = False

# 日志记录
logf = open('log.log', 'a+', encoding='utf-8')
# 是否上传日志,仅上传频道数量等数量的统计信息
is_upload_log = True

# 用户发言频率
user_frequency = {}
# 时间默认值
frequency_time = 60
# 计数默认值
frequency_count = 2

# 公告（可自定义）：
announcement = ""

# 机器人私聊模式
direct_message_mode = True

# 适配pyinstaller
abs_path = os.path.dirname(os.path.realpath(sys.argv[0])) + '/'

# 版本
version = '3.0'

# 语言模型
REV_CHATGPT = 'rev_chatgpt'
OPENAI_OFFICIAL = 'openai_official'
REV_ERNIE = 'rev_ernie'
REV_EDGEGPT = 'rev_edgegpt'
provider = None
chosen_provider = None

# 逆向库对象
rev_chatgpt = None
# gpt配置信息
gpt_config = {}
# 百度内容审核实例
baidu_judge = None
# 回复前缀
reply_prefix = {}
# 关键词回复
keywords = {}

# QQ频道机器人
qqchannel_bot = None
PLATFORM_QQCHAN = 'qqchan'
qqchan_loop = None

# QQ机器人
gocq_bot = None
PLATFORM_GOCQ = 'gocq'
gocq_app = CQHTTP(
    host="127.0.0.1",
    port=6700,
    http_port=5700,
)
gocq_loop = None
nick_qq = "ai "

bing_cache_loop = None


def new_sub_thread(func, args=()):
    thread = threading.Thread(target=func, args=args, daemon=True)
    thread.start()

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
        stat_file = open(abs_path+"configs/stat", 'w', encoding='utf-8')
        stat_file.write(json.dumps(count))
        stat_file.flush()
        stat_file.close()
    except BaseException:
        pass

# 上传统计信息并检查更新
def upload():
    global object_id
    global version
    while True:
        addr = ''
        try:
            # 用户唯一性标识
            addr = requests.get('http://myip.ipip.net', timeout=5).text
        except BaseException:
            pass
        try:
            ts = str(time.time())
            guild_count, guild_msg_count, guild_direct_msg_count, session_count = get_stat()
            headers = {
                'X-LC-Id': 'REDACTED_LEANCLOUD_APP_ID',
                'X-LC-Key': 'REDACTED_LEANCLOUD_APP_KEY',
                'Content-Type': 'application/json'
            }
            key_stat = chatgpt.get_key_stat()
            d = {"data": {'version': version, "guild_count": guild_count, "guild_msg_count": guild_msg_count, "guild_direct_msg_count": guild_direct_msg_count, "session_count": session_count, 'addr': addr, 'key_stat':key_stat}}
            d = json.dumps(d).encode("utf-8")
            res = requests.put(f'https://uqfxtww1.lc-cn-n1-shared.com/1.1/classes/bot_record/{object_id}', headers = headers, data = d)
            if json.loads(res.text)['code'] == 1:
                print("[System] New User.")
                res = requests.post(f'https://uqfxtww1.lc-cn-n1-shared.com/1.1/classes/bot_record', headers = headers, data = d)
                object_id = json.loads(res.text)['objectId']
                object_id_file = open(abs_path+"configs/object_id", 'w+', encoding='utf-8')
                object_id_file.write(str(object_id))
                object_id_file.flush()
                object_id_file.close()
        except BaseException as e:
            pass
        # 每隔2小时上传一次
        time.sleep(60*60*2)

'''
初始化机器人
'''
def initBot(cfg, prov):
    global chatgpt, provider, rev_chatgpt, baidu_judge, rev_edgegpt, chosen_provider
    global reply_prefix, gpt_config, config, uniqueSession, frequency_count, frequency_time,announcement, direct_message_mode, version
    global command_openai_official, command_rev_chatgpt, command_rev_edgegpt,reply_prefix, keywords
    provider = prov
    config = cfg
    if 'reply_prefix' in cfg:
        reply_prefix = cfg['reply_prefix']

    # 语言模型提供商
    if REV_CHATGPT in prov:
        if cfg['rev_ChatGPT']['enable']:
            if 'account' in cfg['rev_ChatGPT']:
                from model.provider.provider_rev_chatgpt import ProviderRevChatGPT
                from model.command.command_rev_chatgpt import CommandRevChatGPT
                rev_chatgpt = ProviderRevChatGPT(cfg['rev_ChatGPT'])
                command_rev_chatgpt = CommandRevChatGPT(cfg['rev_ChatGPT'])
                chosen_provider = REV_CHATGPT
            else:
                input("[System-err] 请退出本程序, 然后在配置文件中填写rev_ChatGPT相关配置")
        
    if REV_EDGEGPT in prov:
        if cfg['rev_edgegpt']['enable']:
            from model.provider.provider_rev_edgegpt import ProviderRevEdgeGPT
            from model.command.command_rev_edgegpt import CommandRevEdgeGPT
            rev_edgegpt = ProviderRevEdgeGPT()
            command_rev_edgegpt = CommandRevEdgeGPT(rev_edgegpt)
            chosen_provider = REV_EDGEGPT
    if OPENAI_OFFICIAL in prov:
        if cfg['openai']['key'] is not None:
            from model.provider.provider_openai_official import ProviderOpenAIOfficial
            from model.command.command_openai_official import CommandOpenAIOfficial
            chatgpt = ProviderOpenAIOfficial(cfg['openai'])
            command_openai_official = CommandOpenAIOfficial(chatgpt)
            chosen_provider = OPENAI_OFFICIAL

    # 得到关键词
    if os.path.exists("keyword.json"):
        with open("keyword.json", 'r', encoding='utf-8') as f:
            keywords = json.load(f)

    # 检查provider设置偏好
    if os.path.exists("provider_preference.txt"):
        with open("provider_preference.txt", 'r', encoding='utf-8') as f:
            res = f.read()
            if res in prov:
                chosen_provider = res
        
    # 百度内容审核
    if 'baidu_aip' in cfg and 'enable' in cfg['baidu_aip'] and cfg['baidu_aip']['enable']:
        try: 
            baidu_judge = BaiduJudge(cfg['baidu_aip'])
            print("[System] 百度内容审核初始化成功")
        except BaseException as e:
            input("[System] 百度内容审核初始化失败: " + str(e))
            exit()
        
    # 统计上传
    if is_upload_log:
        # 读取object_id
        global object_id
        if not os.path.exists(abs_path+"configs/object_id"):
            with open(abs_path+"configs/object_id", 'w', encoding='utf-8') as f:
                f.write("")
        object_id_file = open(abs_path+"configs/object_id", 'r', encoding='utf-8')
        object_id = object_id_file.read()
        object_id_file.close()
        # 创建上传定时器线程
        threading.Thread(target=upload, daemon=True).start()
    
    # 得到私聊模式配置
    if 'direct_message_mode' in cfg:
        direct_message_mode = cfg['direct_message_mode']
        print("[System] 私聊功能: "+str(direct_message_mode))

    # 得到发言频率配置
    if 'limit' in cfg:
        print('[System] 发言频率配置: '+str(cfg['limit']))
        if 'count' in cfg['limit']:
            frequency_count = cfg['limit']['count']
        if 'time' in cfg['limit']:
            frequency_time = cfg['limit']['time']
    
    # 得到公告配置
    if 'notice' in cfg:
        print('[System] 公告配置: '+cfg['notice'])
        announcement += cfg['notice']
    try:
        if 'uniqueSessionMode' in cfg and cfg['uniqueSessionMode']:
            uniqueSession = True
        else:
            uniqueSession = False
        print("[System] 独立会话: " + str(uniqueSession))
        if 'dump_history_interval' in cfg:
            print("[System] 历史记录转储时间周期: " + cfg['dump_history_interval'] + "分钟")
    except BaseException:
        print("[System-Error] 读取uniqueSessionMode/version/dump_history_interval配置文件失败, 使用默认值。")

    print(f"[System] QQ开放平台AppID: {cfg['qqbot']['appid']} 令牌: {cfg['qqbot']['token']}")

    print("\n[System] 如果有任何问题, 请在 https://github.com/Soulter/QQChannelChatGPT 上提交issue说明问题！或者添加QQ：905617992")
    print("[System] 请给 https://github.com/Soulter/QQChannelChatGPT 点个star!")

    if chosen_provider is None:
        print("[System-Warning] 检测到没有启动任何一个语言模型。请至少在配置文件中启用一个语言模型。")

    # 得到指令设置(cmd_config.json)
    if os.path.exists("cmd_config.json"):
        with open("cmd_config.json", 'r', encoding='utf-8') as f:
            cmd_config = json.load(f)
            # QQ机器人昵称
            if 'nick_qq' in cmd_config:
                global nick_qq
                nick_qq = cmd_config['nick_qq']


    thread_inst = None

    # QQ频道
    if 'qqbot' in cfg and cfg['qqbot']['enable']:
        print("[System] 启用QQ频道机器人")
        global qqchannel_bot, qqchan_loop
        qqchannel_bot = QQChan()
        qqchan_loop = asyncio.new_event_loop()
        thread_inst = threading.Thread(target=run_qqchan_bot, args=(cfg, qqchan_loop, qqchannel_bot), daemon=False)
        thread_inst.start()
        # thread.join()

    # GOCQ
    if 'gocqbot' in cfg and cfg['gocqbot']['enable']:
        print("[System] 启用QQ机器人")
        global gocq_app, gocq_bot, gocq_loop
        gocq_bot = QQ()
        gocq_loop = asyncio.new_event_loop()
        thread_inst = threading.Thread(target=run_gocq_bot, args=(gocq_loop, gocq_bot, gocq_app), daemon=False)
        thread_inst.start()

    if thread_inst == None:
        input("[System-Error] 没有启用任何机器人，程序退出")
        exit()

    thread_inst.join()

def run_qqchan_bot(cfg, loop, qqchannel_bot):
    asyncio.set_event_loop(loop)
    intents = botpy.Intents(public_guild_messages=True, direct_message=True) 
    global client
    client = botClient(intents=intents)
    try:
        qqchannel_bot.run_bot(client, cfg['qqbot']['appid'], cfg['qqbot']['token'])
    except BaseException as e:
        input(f"\n[System-Error] 启动QQ频道机器人时出现错误，原因如下：{e}\n可能是没有填写QQBOT appid和token？请在config中完善你的appid和token\n配置教程：https://soulter.top/posts/qpdg.html\n")

def run_gocq_bot(loop, gocq_bot, gocq_app):
    asyncio.set_event_loop(loop)
    global gocq_client
    gocq_client = gocqClient()
    try:
        gocq_bot.run_bot(gocq_app)
    except BaseException as e:
        input("启动QQ机器人出现错误"+str(e))

'''
检查发言频率
'''
def check_frequency(id) -> bool:
    ts = int(time.time())
    if id in user_frequency:
        if ts-user_frequency[id]['time'] > frequency_time:
            user_frequency[id]['time'] = ts
            user_frequency[id]['count'] = 1
            return True
        else:
            if user_frequency[id]['count'] >= frequency_count:
                return False
            else:
                user_frequency[id]['count']+=1
                return True
    else:
        t = {'time':ts,'count':1}
        user_frequency[id] = t
        return True

def save_provider_preference(chosen_provider):
    with open('provider_preference.txt', 'w') as f:
        f.write(chosen_provider)


'''
通用回复方法
'''
def send_message(platform, message, res, msg_ref = None, image = None, gocq_loop = None, qqchannel_bot = None, gocq_bot = None):
    if platform == PLATFORM_QQCHAN:
        if image != None:
            qqchannel_bot.send_qq_msg(message, res, image_mode=True, msg_ref=msg_ref)
        else:
            qqchannel_bot.send_qq_msg(message, res, msg_ref=msg_ref)
    if platform == PLATFORM_GOCQ: 
        if image != None:
            asyncio.run_coroutine_threadsafe(gocq_bot.send_qq_msg(message, image, image_mode=True), gocq_loop).result()
        else:
            asyncio.run_coroutine_threadsafe(gocq_bot.send_qq_msg(message, res), gocq_loop).result()

'''
处理消息
group: 群聊模式
'''
def oper_msg(message, group=False, msg_ref = None, platform = None):
    global session_dict, provider
    qq_msg = ''
    session_id = ''
    user_id = ''
    user_name = ''
    global chosen_provider, reply_prefix, keywords, qqchannel_bot, gocq_bot, gocq_loop, bing_cache_loop
    role = "member" # 角色
    hit = False # 是否命中指令
    command_result = () # 调用指令返回的结果

    if platform == PLATFORM_QQCHAN:
        print("[QQCHAN-BOT] 接收到消息："+ str(message.content))
        user_id = message.author.id
        user_name = message.author.username
        global qqchan_loop
    if platform == PLATFORM_GOCQ:
        if isinstance(message.message[0], Plain):
            print("[GOCQ-BOT] 接收到消息："+ str(message.message[0].text))
        elif isinstance(message.message[0], At):
            print("[GOCQ-BOT] 接收到消息："+ str(message.message[1].text))
            
        user_id = message.user_id
        user_name = message.user_id
        global gocq_loop
    
    if chosen_provider is None:
        send_message(platform, message,  f"没有启动任何一个语言模型。请至少在配置文件中启用一个语言模型。", msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)
    
    # 检查发言频率
    if not check_frequency(user_id):
        qqchannel_bot.send_qq_msg(message, f'{user_name}的发言超过频率限制(╯▔皿▔)╯。\n{frequency_time}秒内只能提问{frequency_count}次。')
        return

    if platform == PLATFORM_QQCHAN:
        if group:
            # 频道内
            # 过滤@
            qq_msg = message.content
            lines = qq_msg.splitlines()
            for i in range(len(lines)):
                lines[i] = re.sub(r"<@!\d+>", "", lines[i])
            qq_msg = "\n".join(lines).lstrip().strip()
            if uniqueSession:
                session_id = user_id
            else:
                session_id = message.channel_id
            # 得到身份
            if "2" in message.member.roles or "4" in message.member.roles or "5" in message.member.roles:
                print("[QQCHAN-BOT] 检测到管理员身份")
                role = "admin"
            else:
                role = "member"
        else:
            # 私信
            qq_msg = message.content
            session_id = user_id

    if platform == PLATFORM_GOCQ:
        if group:
            if isinstance(message.message[0], Plain):
                qq_msg = str(message.message[0].text)
            elif isinstance(message.message[0], At):
                qq_msg = str(message.message[1].text).strip()
            else:
                return
            session_id = message.group_id
        else:
            qq_msg = message.message[0].text
            session_id = message.user_id
        # todo: 暂时将所有人设为管理员
        role = "admin"
        
    logf.write("[QQBOT] "+ qq_msg+'\n')
    logf.flush()

    # 关键词回复
    for k in keywords:
        if qq_msg == k:
            send_message(platform, message, keywords[k], msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)
            return

    # 关键词拦截器
    for i in uw.unfit_words_q:
        matches = re.match(i, qq_msg.strip(), re.I | re.M)
        if matches:
            send_message(platform, message,  f"你的提问得到的回复未通过【自有关键词拦截】服务, 不予回复。", msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)
            return
    if baidu_judge != None:
        check, msg = baidu_judge.judge(qq_msg)
        if not check:
            send_message(platform, message,  f"你的提问得到的回复未通过【百度AI内容审核】服务, 不予回复。\n\n{msg}", msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)
            return
    
    # 检查是否是更换语言模型的请求
    temp_switch = ""
    if qq_msg.startswith('/bing') or qq_msg.startswith('/gpt') or qq_msg.startswith('/revgpt'):
        target = chosen_provider
        if qq_msg.startswith('/bing'):
            target = REV_EDGEGPT
        elif qq_msg.startswith('/gpt'):
            target = OPENAI_OFFICIAL
        elif qq_msg.startswith('/revgpt'):
            target = REV_CHATGPT
        l = qq_msg.split(' ')
        if len(l) > 1 and l[1] != "":
            # 临时对话模式，先记录下之前的语言模型，回答完毕后再切回
            temp_switch = chosen_provider
            chosen_provider = target
            qq_msg = l[1]
        else:
            # if role != "admin":
            #     send_message(platform, message, "你没有权限更换语言模型。", msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)
            #     return
            chosen_provider = target
            save_provider_preference(chosen_provider)
            send_message(platform, message, f"已切换至【{chosen_provider}】", msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)
            return

    chatgpt_res = ""

    if chosen_provider == OPENAI_OFFICIAL: 
        hit, command_result = command_openai_official.check_command(qq_msg, session_id, user_name, role, platform=platform)
        # hit: 是否触发了指令.
        if not hit:
            # 请求ChatGPT获得结果
            try:
                chatgpt_res = chatgpt.text_chat(qq_msg, session_id)
                if OPENAI_OFFICIAL in reply_prefix:
                    chatgpt_res = reply_prefix[OPENAI_OFFICIAL] + chatgpt_res
            except (BaseException) as e:
                print("[System-Err] OpenAI API错误。原因如下:\n"+str(e))
                send_message(platform, message, f"OpenAI API错误。原因如下：\n{str(e)} \n前往官方频道反馈~", msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)

    elif chosen_provider == REV_CHATGPT:
        hit, command_result = command_rev_chatgpt.check_command(qq_msg, role, platform=platform)
        if not hit:
            try:
                chatgpt_res = str(rev_chatgpt.text_chat(qq_msg))
                if REV_CHATGPT in reply_prefix:
                    chatgpt_res = reply_prefix[REV_CHATGPT] + chatgpt_res
            except BaseException as e:
                print("[System-Err] Rev ChatGPT API错误。原因如下:\n"+str(e))
                send_message(platform, message, f"Rev ChatGPT API错误。原因如下：\n{str(e)} \n前往官方频道反馈~", msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)

    elif chosen_provider == REV_EDGEGPT:
        if bing_cache_loop == None:
            if platform == PLATFORM_GOCQ:
                bing_cache_loop = gocq_loop
            elif platform == PLATFORM_QQCHAN:
                bing_cache_loop = qqchan_loop
        hit, command_result = command_rev_edgegpt.check_command(qq_msg, bing_cache_loop, role, platform=platform)
        if not hit:
            try:
                while rev_edgegpt.is_busy():
                    time.sleep(1)

                res, res_code = asyncio.run_coroutine_threadsafe(rev_edgegpt.text_chat(qq_msg), bing_cache_loop).result()
                if res_code == 0: # bing不想继续话题，重置会话后重试。
                    send_message(platform, message, "Bing不想继续话题了, 正在自动重置会话并重试。", msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)
                    asyncio.run_coroutine_threadsafe(rev_edgegpt.forget(), bing_cache_loop).result()
                    res, res_code = asyncio.run_coroutine_threadsafe(rev_edgegpt.text_chat(qq_msg), bing_cache_loop).result()
                    if res_code == 0: # bing还是不想继续话题，大概率说明提问有问题。
                        asyncio.run_coroutine_threadsafe(rev_edgegpt.forget(), bing_cache_loop).result()
                        send_message(platform, message, "Bing仍然不想继续话题, 会话已重置, 请检查您的提问后重试。", msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)
                        res = ""
                chatgpt_res = str(res)
                if REV_EDGEGPT in reply_prefix:
                    chatgpt_res = reply_prefix[REV_EDGEGPT] + chatgpt_res
            except BaseException as e:
                print("[System-Err] Rev NewBing API错误。原因如下:\n"+str(e))
                send_message(platform, message, f"Rev NewBing API错误。原因如下：\n{str(e)} \n前往官方频道反馈~", msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)

    # 切换回原来的语言模型
    if temp_switch != "":
        chosen_provider = temp_switch
        
    # 指令回复
    if hit:
        # 检查指令. command_result是一个元组：(指令调用是否成功, 指令返回的文本结果, 指令类型)
        if command_result != None:
            command = command_result[2]
            if command == "keyword":
                with open("keyword.json", "r", encoding="utf-8") as f:
                    keywords = json.load(f)

            # QQ昵称
            if command == "nick":
                with open("cmd_config.json", "r", encoding="utf-8") as f:
                    global nick_qq
                    nick_qq = json.load(f)["nick_qq"]

            if command_result[0]:
                # 是否是画图指令
                if len(command_result) == 3 and command_result[2] == 'draw':
                    for i in command_result[1]:
                        send_message(platform, message, i, msg_ref=msg_ref, image=i, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)
                else: 
                    try:
                        send_message(platform, message, command_result[1], msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)
                    except BaseException as e:
                        t = command_result[1].replace(".", " . ")
                        send_message(platform, message, t, msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)

            else:
                send_message(platform, message, f"指令调用错误: \n{command_result[1]}", msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)

        return
    
    if chatgpt_res == "":
        return

    # 记录日志
    logf.write(f"{reply_prefix} {str(chatgpt_res)}\n")
    logf.flush()

    # 敏感过滤
    # 过滤不合适的词
    judged_res = chatgpt_res
    for i in uw.unfit_words:
        judged_res = re.sub(i, "***", judged_res)
    # 百度内容审核服务二次审核
    if baidu_judge != None:
        check, msg = baidu_judge.judge(judged_res)
        if not check:
            send_message(platform, message, f"你的提问得到的回复【百度内容审核】未通过，不予回复。\n\n{msg}", msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)
            return
        
    # 发送qq信息
    try:
        send_message(platform, message, chatgpt_res, msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)
    except BaseException as e:
        print("回复消息错误: \n"+str(e))

'''
获取统计信息
'''
def get_stat(self):

    try:
        f = open(abs_path+"configs/stat", "r", encoding="utf-8")
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

        f = open(abs_path+"configs/session", "r", encoding="utf-8")
        fjson = json.loads(f.read())
        f.close()
        for k,v in fjson.items():
            session_count += 1
        return guild_count, guild_msg_count, guild_direct_msg_count, session_count
    except:
        return -1, -1, -1, -1
    

# QQ频道机器人
class botClient(botpy.Client):
    # 收到频道消息
    async def on_at_message_create(self, message: Message):
        toggle_count(at=True, message=message)
        message_reference = Reference(message_id=message.id, ignore_get_message_error=False)
        new_sub_thread(oper_msg, (message, True, message_reference, PLATFORM_QQCHAN))

    # 收到私聊消息
    async def on_direct_message_create(self, message: DirectMessage):
        if direct_message_mode:
            toggle_count(at=False, message=message)
            new_sub_thread(oper_msg, (message, False, None, PLATFORM_QQCHAN))
# QQ机器人
class gocqClient():
    # 收到群聊消息
    @gocq_app.receiver("GroupMessage")
    async def _(app: CQHTTP, source: GroupMessage):
        global nick_qq
        if isinstance(source.message[0], Plain):
            if source.message[0].text.startswith(nick_qq):
                source.message[0].text = source.message[0].text[len(nick_qq):]
                new_sub_thread(oper_msg, (source, True, None, PLATFORM_GOCQ))
        if isinstance(source.message[0], At):
            if source.message[0].qq == source.self_id:
                if source.message[1].text.startswith(nick_qq):
                    source.message[1].text = source.message[0].text[len(nick_qq):]
                new_sub_thread(oper_msg, (source, True, None, PLATFORM_GOCQ))
        else:
            return
        
    @gocq_app.receiver("FriendMessage")
    async def _(app: CQHTTP, source: FriendMessage):
        if isinstance(source.message[0], Plain):
            new_sub_thread(oper_msg, (source, False, None, PLATFORM_GOCQ))
        else:
            return
        
    @gocq_app.receiver("GroupMemberIncrease")
    async def _(app: CQHTTP, source: GroupMemberIncrease):
        global nick_qq
        await app.sendGroupMessage(source.group_id, [
            Plain(text=f"欢迎加入本群！\n欢迎给https://github.com/Soulter/QQChannelChatGPT项目一个Star😊~\n@我输入help查看帮助~\n我叫{nick_qq}, 你也可以以【{nick_qq}+问题】的格式来提醒我并问我问题哦~\n")
        ])