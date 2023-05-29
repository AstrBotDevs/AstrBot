import botpy
from botpy.message import Message, DirectMessage
from botpy.types.message import Reference
import re
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
    FriendMessage,
    GuildMessage
)
from nakuru.entities.components import Plain,At
from model.command.command import Command
from model.command.command_rev_chatgpt import CommandRevChatGPT
from model.command.command_rev_edgegpt import CommandRevEdgeGPT
from model.command.command_openai_official import CommandOpenAIOfficial
from util import general_utils as gu
from util import cmd_config as CmdConfig



# QQBotClient实例
client = ''
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
# logf = open('log.log', 'a+', encoding='utf-8')
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
version = '3.0.2'

# 语言模型
REV_CHATGPT = 'rev_chatgpt'
OPENAI_OFFICIAL = 'openai_official'
REV_ERNIE = 'rev_ernie'
REV_EDGEGPT = 'rev_edgegpt'
provider = None
chosen_provider = None

# 语言模型对象
rev_chatgpt = None
rev_edgegpt = None
chatgpt = None
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
admin_qq = "123456"

gocq_loop = None
nick_qq = None

bing_cache_loop = None

# 插件
cached_plugins = {}

# 统计
cnt_total = 0
cnt_valid = 0

# 新版配置文件
cc = CmdConfig.CmdConfig()
cc.init_attributes(["qq_forward_threshold"], 200)


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
    global version, cnt_valid, cnt_total
    while True:
        addr = ''
        addr_ip = ''
        try:
            addr = requests.get('http://myip.ipip.net', timeout=5).text
            addr_ip = re.findall(r'\d+.\d+.\d+.\d+', addr)[0]
        except BaseException as e:
            print(e)
            pass
        try:
            o = {"cnt_total": cnt_total,"admin": admin_qq,"addr": addr,}
            o_j = json.dumps(o)
            res = {"version": version, "count": cnt_valid, "ip": addr_ip, "others": o_j}
            resp = requests.post('https://api.soulter.top/upload', data=json.dumps(res), timeout=5)
            # print(resp.text)
            if resp.status_code == 200:
                ok = resp.json()
                if ok['status'] == 'ok':
                    cnt_valid = 0
                    cnt_total = 0
        except BaseException as e:
            print(e)
            pass
        time.sleep(60*10)

'''
初始化机器人
'''
def initBot(cfg, prov):
    global chatgpt, provider, rev_chatgpt, baidu_judge, rev_edgegpt, chosen_provider
    global reply_prefix, gpt_config, config, uniqueSession, frequency_count, frequency_time,announcement, direct_message_mode, version
    global command_openai_official, command_rev_chatgpt, command_rev_edgegpt,reply_prefix, keywords, cached_plugins
    provider = prov
    config = cfg
    if 'reply_prefix' in cfg:
        reply_prefix = cfg['reply_prefix']

    # 语言模型提供商
    gu.log("--------加载语言模型--------", gu.LEVEL_INFO, fg=gu.FG_COLORS['yellow'])

    if REV_CHATGPT in prov:
        gu.log("- 逆向ChatGPT库 -", gu.LEVEL_INFO)
        if cfg['rev_ChatGPT']['enable']:
            if 'account' in cfg['rev_ChatGPT']:
                from model.provider.provider_rev_chatgpt import ProviderRevChatGPT
                rev_chatgpt = ProviderRevChatGPT(cfg['rev_ChatGPT'])
                chosen_provider = REV_CHATGPT
            else:
                input("[System-err] 请退出本程序, 然后在配置文件中填写rev_ChatGPT相关配置")
        
    if REV_EDGEGPT in prov:
        gu.log("- New Bing -", gu.LEVEL_INFO)

        if not os.path.exists('./cookies.json'):
            input("[System-err] 导入Bing模型时发生错误, 没有找到cookies文件或者cookies文件放置位置错误。windows启动器启动的用户请把cookies.json文件放到和启动器相同的目录下。\n如何获取请看https://github.com/Soulter/QQChannelChatGPT仓库介绍。")
        else:
            if cfg['rev_edgegpt']['enable']:
                try:
                    from model.provider.provider_rev_edgegpt import ProviderRevEdgeGPT
                    rev_edgegpt = ProviderRevEdgeGPT()
                    chosen_provider = REV_EDGEGPT
                except BaseException as e:
                    gu.log("加载Bing模型时发生错误, 请检查1. cookies文件是否正确放置 2. 是否设置了代理（梯子）。", gu.LEVEL_ERROR, max_len=60)
    if OPENAI_OFFICIAL in prov:
        gu.log("- OpenAI官方 -", gu.LEVEL_INFO)
        if cfg['openai']['key'] is not None:
            from model.provider.provider_openai_official import ProviderOpenAIOfficial
            chatgpt = ProviderOpenAIOfficial(cfg['openai'])
            chosen_provider = OPENAI_OFFICIAL

    command_rev_edgegpt = CommandRevEdgeGPT(rev_edgegpt)
    command_rev_chatgpt = CommandRevChatGPT(rev_chatgpt)
    command_openai_official = CommandOpenAIOfficial(chatgpt)

    gu.log("--------加载个性化配置--------", gu.LEVEL_INFO, fg=gu.FG_COLORS['yellow'])
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
            gu.log("百度内容审核初始化成功", gu.LEVEL_INFO)
        except BaseException as e:
            gu.log("百度内容审核初始化失败", gu.LEVEL_ERROR)
        
    threading.Thread(target=upload, daemon=True).start()
    
    # 得到私聊模式配置
    if 'direct_message_mode' in cfg:
        direct_message_mode = cfg['direct_message_mode']
        gu.log("私聊功能: "+str(direct_message_mode), gu.LEVEL_INFO)

    # 得到发言频率配置
    if 'limit' in cfg:
        gu.log("发言频率配置: "+str(cfg['limit']), gu.LEVEL_INFO)
        if 'count' in cfg['limit']:
            frequency_count = cfg['limit']['count']
        if 'time' in cfg['limit']:
            frequency_time = cfg['limit']['time']
    
    # 得到公告配置
    if 'notice' in cfg:
        gu.log("公告配置: "+cfg['notice'], gu.LEVEL_INFO)
        announcement += cfg['notice']
    try:
        if 'uniqueSessionMode' in cfg and cfg['uniqueSessionMode']:
            uniqueSession = True
        else:
            uniqueSession = False
        gu.log("独立会话: "+str(uniqueSession), gu.LEVEL_INFO)
        if 'dump_history_interval' in cfg:
            gu.log("历史记录保存间隔: "+str(cfg['dump_history_interval']), gu.LEVEL_INFO)
    except BaseException:
        pass

    
    gu.log(f"QQ开放平台AppID: {cfg['qqbot']['appid']} 令牌: {cfg['qqbot']['token']}")

    if chosen_provider is None:
        gu.log("检测到没有启动任何一个语言模型。请至少在配置文件中启用一个语言模型。", gu.LEVEL_CRITICAL)

    global nick_qq
    nick_qq = cc.get('nick_qq', nick_qq)

    thread_inst = None

    gu.log("--------加载插件--------", gu.LEVEL_INFO, fg=gu.FG_COLORS['yellow'])
    # 加载插件
    _command = Command(None)
    ok, err = _command.plugin_reload(cached_plugins)
    if ok:
        gu.log("加载插件完成", gu.LEVEL_INFO)
    else:
        gu.log(err, gu.LEVEL_ERROR)

    gu.log("--------加载平台--------", gu.LEVEL_INFO, fg=gu.FG_COLORS['yellow'])
    # GOCQ
    global gocq_bot

    if 'gocqbot' in cfg and cfg['gocqbot']['enable']:
        gu.log("- 启用QQ机器人 -", gu.LEVEL_INFO)

        global admin_qq, admin_qqchan
        admin_qq = cc.get('admin_qq', None)
        admin_qqchan = cc.get('admin_qqchan', None)
        if admin_qq == None:
            gu.log("未设置管理者QQ号(管理者才能使用update/plugin等指令)", gu.LEVEL_WARNING)
            admin_qq = input("请输入管理者QQ号(必须设置): ")
            gu.log("管理者QQ号设置为: " + admin_qq, gu.LEVEL_INFO, fg=gu.FG_COLORS['yellow'])
            cc.put('admin_qq', admin_qq)
        if admin_qqchan == None:
            gu.log("未设置管理者QQ频道用户号(管理者才能使用update/plugin等指令)", gu.LEVEL_WARNING)
            admin_qqchan = input("请输入管理者频道用户号(不是QQ号, 可以先回车跳过然后在频道发送指令!myid获取): ")
            if admin_qqchan == "":
                gu.log("跳过设置管理者频道用户号", gu.LEVEL_INFO, fg=gu.FG_COLORS['yellow'])
            else:
                gu.log("管理者频道用户号设置为: " + admin_qqchan, gu.LEVEL_INFO, fg=gu.FG_COLORS['yellow'])
                cc.put('admin_qqchan', admin_qqchan)
        
        gu.log("管理者QQ: " + admin_qq, gu.LEVEL_INFO)
        gu.log("管理者频道用户号: " + admin_qqchan, gu.LEVEL_INFO)
        
        global gocq_app, gocq_loop
        gocq_loop = asyncio.new_event_loop()
        gocq_bot = QQ(True, cc, gocq_loop)
        thread_inst = threading.Thread(target=run_gocq_bot, args=(gocq_loop, gocq_bot, gocq_app), daemon=False)
        thread_inst.start()
    else:
        gocq_bot = QQ(False)

    gu.log("机器人部署教程: https://github.com/Soulter/QQChannelChatGPT/wiki/", gu.LEVEL_INFO, fg=gu.FG_COLORS['yellow'])
    gu.log("如果有任何问题, 请在 https://github.com/Soulter/QQChannelChatGPT 上提交issue说明问题！", gu.LEVEL_INFO, fg=gu.FG_COLORS['yellow'])
    gu.log("请给 https://github.com/Soulter/QQChannelChatGPT 点个star!", gu.LEVEL_INFO, fg=gu.FG_COLORS['yellow'])

    # QQ频道
    if 'qqbot' in cfg and cfg['qqbot']['enable']:
        gu.log("- 启用QQ频道机器人(旧版) -", gu.LEVEL_INFO)
        global qqchannel_bot, qqchan_loop
        qqchannel_bot = QQChan()
        qqchan_loop = asyncio.new_event_loop()
        thread_inst = threading.Thread(target=run_qqchan_bot, args=(cfg, qqchan_loop, qqchannel_bot), daemon=False)
        thread_inst.start()
        # thread.join()

    if thread_inst == None:
        input("[System-Error] 没有启用/成功启用任何机器人，程序退出")
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
        gu.log("启动QQ频道机器人时出现错误, 原因如下: " + str(e), gu.LEVEL_CRITICAL, tag="QQ频道")
        gu.log(r"【提醒】有可能你想启动的是gocq, 并不是这个旧版的QQ频道SDK, 如果是这样, 请修改配置文件（QQChannelChatGPT/config.yaml）详情请看：https://github.com/Soulter/QQChannelChatGPT/wiki/%E4%BA%8C%E3%80%81%E9%A1%B9%E7%9B%AE%E9%85%8D%E7%BD%AE%E6%96%87%E4%BB%B6%E9%85%8D%E7%BD%AE。" + str(e), gu.LEVEL_CRITICAL, tag="QQ频道")
        # gu.log("如果你使用了go-cqhttp, 则可以忽略上面的报错。" + str(e), gu.LEVEL_CRITICAL, tag="QQ频道")
        # input(f"\n[System-Error] 启动QQ频道机器人时出现错误，原因如下：{e}\n可能是没有填写QQBOT appid和token？请在config中完善你的appid和token\n配置教程：https://soulter.top/posts/qpdg.html\n")

def run_gocq_bot(loop, gocq_bot, gocq_app):
    asyncio.set_event_loop(loop)
    gu.log("正在检查本地GO-CQHTTP连接...端口5700, 6700", tag="QQ")
    while True:
        if not gu.port_checker(5700) or not gu.port_checker(6700):
            gu.log("与GO-CQHTTP通信失败, 请检查GO-CQHTTP是否启动并正确配置。5秒后自动重试。", gu.LEVEL_CRITICAL, tag="QQ")
            time.sleep(5)
        else:
            gu.log("检查完毕，未发现问题。", tag="QQ")
            break


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
    global cnt_valid
    cnt_valid += 1
    if platform == PLATFORM_QQCHAN:
        if image != None:
            qqchannel_bot.send_qq_msg(message, str(res), image_mode=True, msg_ref=msg_ref)
        else:
            qqchannel_bot.send_qq_msg(message, str(res), msg_ref=msg_ref)
    if platform == PLATFORM_GOCQ: 
        if image != None:
            asyncio.run_coroutine_threadsafe(gocq_bot.send_qq_msg(message, image, image_mode=True), gocq_loop).result()
        else:
            asyncio.run_coroutine_threadsafe(gocq_bot.send_qq_msg(message, res, False, ), gocq_loop).result()


def oper_msg(message, 
             group: bool=False, 
             msg_ref: Reference = None, 
             platform: str = None):
    """
    处理消息。
    group: 群聊模式,
    message: 频道是频道的消息对象, QQ是nakuru-gocq的消息对象
    """
    global session_dict, provider
    qq_msg = ''
    session_id = ''
    user_id = ''
    user_name = ''
    global chosen_provider, reply_prefix, keywords, qqchannel_bot, gocq_bot, gocq_loop, bing_cache_loop, qqchan_loop
    role = "member" # 角色
    hit = False # 是否命中指令
    command_result = () # 调用指令返回的结果
    global admin_qq, admin_qqchan, cached_plugins, gocq_bot, nick_qq
    global cnt_total

    cnt_total += 1

    with_tag = False # 是否带有昵称

    # 将nick_qq(昵称)统一转换为tuple
    if nick_qq == None:
        nick_qq = ("ai","!","！")
    if isinstance(nick_qq, str):
        nick_qq = (nick_qq,)
    if isinstance(nick_qq, list):
        nick_qq = tuple(nick_qq)    

    if platform == PLATFORM_QQCHAN:
        with_tag = True
        gu.log(f"收到消息：{message.content}", gu.LEVEL_INFO, tag="QQ频道")
        user_id = message.author.id
        user_name = message.author.username
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
                # gu.log(f"检测到管理员身份", gu.LEVEL_INFO, tag="QQ频道")
                role = "admin"
            else:
                role = "member"
        else:
            # 私信
            qq_msg = message.content
            session_id = user_id

    if platform == PLATFORM_GOCQ:
        _len = 0
        for i in message.message:
            if isinstance(i, Plain):
                qq_msg += str(i.text).strip()
            if isinstance(i, At):
                # @机器人
                if message.type == "GuildMessage":
                    if i.qq == message.self_tiny_id:
                        with_tag = True
                if message.type == "FriendMessage":
                    if i.qq == message.self_id:
                        with_tag = True
                if message.type == "GroupMessage":
                    if i.qq == message.self_id:
                        with_tag = True
           
        for i in nick_qq:
            if i != '' and qq_msg.startswith(i):
                _len = len(i)
                with_tag = True
                break
        qq_msg = qq_msg[_len:].strip()

        gu.log(f"收到消息：{qq_msg}", gu.LEVEL_INFO, tag="QQ")
        user_id = message.user_id

        if group:
            # 适配GO-CQHTTP的频道功能
            if message.type == "GuildMessage":
                session_id = message.channel_id
            else:
                session_id = message.group_id
        else:
            with_tag = True
            # qq_msg = message.message[0].text
            session_id = message.user_id
        role = "member"

        if message.type == "GuildMessage":
            sender_id = str(message.sender.tiny_id)
        else:
            sender_id = str(message.sender.user_id)
        if sender_id == admin_qq or sender_id == admin_qqchan:
            # gu.log("检测到管理员身份", gu.LEVEL_INFO, tag="GOCQ")
            role = "admin"

    if qq_msg == "":
        send_message(platform, message,  f"Hi~", msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)
        return
    
    if with_tag:
        # 检查发言频率
        if not check_frequency(user_id):
            send_message(platform, message, f'你的发言超过频率限制(╯▔皿▔)╯。\n管理员设置{frequency_time}秒内只能提问{frequency_count}次。', msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)
            return

    # logf.write("[GOCQBOT] "+ qq_msg+'\n')
    # logf.flush()

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
        hit, command_result = command_openai_official.check_command(qq_msg, session_id, user_name, role, platform=platform, message_obj=message, cached_plugins=cached_plugins, qq_platform=gocq_bot)
        # hit: 是否触发了指令
        if not hit:
            if not with_tag:
                return
            if chatgpt == None:
                send_message(platform, message, f"管理员未启动OpenAI模型或初始化时失败。", msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)
                return
            # 请求ChatGPT获得结果
            try:
                chatgpt_res = chatgpt.text_chat(qq_msg, session_id)
                if OPENAI_OFFICIAL in reply_prefix:
                    chatgpt_res = reply_prefix[OPENAI_OFFICIAL] + chatgpt_res
            except (BaseException) as e:
                gu.log("OpenAI API请求错误, 原因: "+str(e), gu.LEVEL_ERROR)
                send_message(platform, message, f"OpenAI API错误, 原因: {str(e)}", msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)

    elif chosen_provider == REV_CHATGPT:
        hit, command_result = command_rev_chatgpt.check_command(qq_msg, role, platform=platform, message_obj=message, cached_plugins=cached_plugins, qq_platform=gocq_bot)
        if not hit:
            if not with_tag:
                return
            if rev_chatgpt == None:
                send_message(platform, message, f"管理员未启动此模型或者此模型初始化时失败。", msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)
                return
            try:
                while rev_chatgpt.is_all_busy():
                    time.sleep(1)
                chatgpt_res = str(rev_chatgpt.text_chat(qq_msg))
                if REV_CHATGPT in reply_prefix:
                    chatgpt_res = reply_prefix[REV_CHATGPT] + chatgpt_res
            except BaseException as e:
                gu.log("逆向ChatGPT请求错误, 原因: "+str(e), gu.LEVEL_ERROR)
                send_message(platform, message, f"RevChatGPT错误, 原因: \n{str(e)}", msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)

    elif chosen_provider == REV_EDGEGPT:
        if bing_cache_loop == None:
            if platform == PLATFORM_GOCQ:
                bing_cache_loop = gocq_loop
            elif platform == PLATFORM_QQCHAN:
                bing_cache_loop = qqchan_loop
        hit, command_result = command_rev_edgegpt.check_command(qq_msg, bing_cache_loop, role, platform=platform, message_obj=message, cached_plugins=cached_plugins, qq_platform=gocq_bot)
        if not hit:
            try:
                if not with_tag:
                    return
                if rev_edgegpt == None:
                    send_message(platform, message, f"管理员未启动此模型或者此模型初始化时失败。", msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)
                    return
                while rev_edgegpt.is_busy():
                    time.sleep(1)

                res, res_code = asyncio.run_coroutine_threadsafe(rev_edgegpt.text_chat(qq_msg, platform), bing_cache_loop).result()
                if res_code == 0: # bing不想继续话题，重置会话后重试。
                    send_message(platform, message, "Bing不想继续话题了, 正在自动重置会话并重试。", msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)
                    asyncio.run_coroutine_threadsafe(rev_edgegpt.forget(), bing_cache_loop).result()
                    res, res_code = asyncio.run_coroutine_threadsafe(rev_edgegpt.text_chat(qq_msg, platform), bing_cache_loop).result()
                    if res_code == 0: # bing还是不想继续话题，大概率说明提问有问题。
                        asyncio.run_coroutine_threadsafe(rev_edgegpt.forget(), bing_cache_loop).result()
                        send_message(platform, message, "Bing仍然不想继续话题, 会话已重置, 请检查您的提问后重试。", msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)
                        res = ""
                chatgpt_res = str(res)
                if REV_EDGEGPT in reply_prefix:
                    chatgpt_res = reply_prefix[REV_EDGEGPT] + chatgpt_res
            except BaseException as e:
                gu.log("NewBing请求错误, 原因: "+str(e), gu.LEVEL_ERROR)
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
                if os.path.exists("keyword.json"):
                    with open("keyword.json", "r", encoding="utf-8") as f:
                        keywords = json.load(f)

            # 昵称
            if command == "nick":
                nick_qq = cc.get("nick_qq", nick_qq)

            if command_result[0]:
                # 是否是画图指令
                if isinstance(command_result[1], list) and len(command_result) == 3 and command_result[2] == 'draw':
                    if chatgpt != None:
                        for i in command_result[1]:
                            send_message(platform, message, i, msg_ref=msg_ref, image=i, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)
                    else:
                        send_message(platform, message, "画图指令需要启用OpenAI官方模型.", msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)
                else:
                    try:
                        send_message(platform, message, command_result[1], msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)
                    except BaseException as e:
                        send_message(platform, message, f"回复消息出错: {str(e)}", msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)

            else:
                send_message(platform, message, f"指令调用错误: \n{str(command_result[1])}", msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)

        return
    
    if chatgpt_res == "":
        return

    # 记录日志
    # logf.write(f"{reply_prefix} {str(chatgpt_res)}\n")
    # logf.flush()

    # 敏感过滤
    # 过滤不合适的词
    for i in uw.unfit_words:
        chatgpt_res = re.sub(i, "***", chatgpt_res)
    # 百度内容审核服务二次审核
    if baidu_judge != None:
        check, msg = baidu_judge.judge(chatgpt_res)
        if not check:
            send_message(platform, message, f"你的提问得到的回复【百度内容审核】未通过，不予回复。\n\n{msg}", msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)
            return
        
    # 发送qq信息
    try:
        send_message(platform, message, chatgpt_res, msg_ref=msg_ref, gocq_loop=gocq_loop, qqchannel_bot=qqchannel_bot, gocq_bot=gocq_bot)
    except BaseException as e:
        gu.log("回复消息错误: \n"+str(e), gu.LEVEL_ERROR)

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
        # gu.log(str(source), gu.LEVEL_INFO, max_len=9999)

        if isinstance(source.message[0], Plain):
            new_sub_thread(oper_msg, (source, True, None, PLATFORM_GOCQ))
        if isinstance(source.message[0], At):
            if source.message[0].qq == source.self_id:
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
            Plain(text=f"欢迎加入本群！\n欢迎给https://github.com/Soulter/QQChannelChatGPT项目一个Star😊~\n@我输入help查看帮助~\n")
        ])

    @gocq_app.receiver("GuildMessage")
    async def _(app: CQHTTP, source: GuildMessage):
        # gu.log(str(source), gu.LEVEL_INFO, max_len=9999)

        if isinstance(source.message[0], Plain):
            # if source.message[0].text.startswith(nick_qq):
            #     _len = 0
            #     for i in nick_qq:
            #         if source.message[0].text.startswith(i):
            #             _len = len(i)
            #     source.message[0].text = source.message[0].text[_len:].strip()
            new_sub_thread(oper_msg, (source, True, None, PLATFORM_GOCQ))
        if isinstance(source.message[0], At):
            if source.message[0].qq == source.self_tiny_id:
                new_sub_thread(oper_msg, (source, True, None, PLATFORM_GOCQ))
        else:
            return