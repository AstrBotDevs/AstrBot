import botpy
from botpy.message import Message, DirectMessage
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
from model.platform.qqchan import QQChan, NakuruGuildMember, NakuruGuildMessage
from model.platform.qq import QQ
from model.platform.qqgroup import (
    UnofficialQQBotSDK,
    Event as QQEvent,
    Message as QQMessage,
    MessageChain,
    PlainText
)
from nakuru import (
    CQHTTP,
    GroupMessage,
    GroupMemberIncrease,
    FriendMessage,
    GuildMessage,
    Notify
)
from nakuru.entities.components import Plain,At,Image
from model.provider.provider import Provider
from model.command.command import Command
from util import general_utils as gu
from util.cmd_config import CmdConfig as cc
import util.function_calling.gplugin as gplugin
import util.plugin_util as putil
from PIL import Image as PILImage
import io
import traceback
from . global_object import GlobalObject
from typing import Union, Callable
from addons.dashboard.helper import DashBoardHelper
from addons.dashboard.server import DashBoardData
from cores.monitor.perf import run_monitor
from cores.database.conn import dbConn

# 缓存的会话
session_dict = {}
# 统计信息
count = {}
# 统计信息
stat_file = ''

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

# 版本
version = '3.1.0'

# 语言模型
REV_CHATGPT = 'rev_chatgpt'
OPENAI_OFFICIAL = 'openai_official'
REV_ERNIE = 'rev_ernie'
REV_EDGEGPT = 'rev_edgegpt'
NONE_LLM = 'none_llm'
chosen_provider = None

# 语言模型对象
llm_instance: dict[str, Provider] = {}
llm_command_instance: dict[str, Command] = {}

# 百度内容审核实例
baidu_judge = None
# 关键词回复
keywords = {}

# QQ频道机器人
qqchannel_bot: QQChan = None
PLATFORM_QQCHAN = 'qqchan'
qqchan_loop = None
client = None

# QQ群机器人
PLATFROM_QQBOT = 'qqbot'

# CLI
PLATFORM_CLI = 'cli'

# 加载默认配置
cc.init_attributes("qq_forward_threshold", 200)
cc.init_attributes("qq_welcome", "欢迎加入本群！\n欢迎给https://github.com/Soulter/QQChannelChatGPT项目一个Star😊~\n输入help查看帮助~\n")
cc.init_attributes("bing_proxy", "")
cc.init_attributes("qq_pic_mode", False)
cc.init_attributes("rev_chatgpt_model", "")
cc.init_attributes("rev_chatgpt_plugin_ids", [])
cc.init_attributes("rev_chatgpt_PUID", "")
cc.init_attributes("rev_chatgpt_unverified_plugin_domains", [])
cc.init_attributes("gocq_host", "127.0.0.1")
cc.init_attributes("gocq_http_port", 5700)
cc.init_attributes("gocq_websocket_port", 6700)
cc.init_attributes("gocq_react_group", True)
cc.init_attributes("gocq_react_guild", True)
cc.init_attributes("gocq_react_friend", True)
cc.init_attributes("gocq_react_group_increase", True)
cc.init_attributes("gocq_qqchan_admin", "")
cc.init_attributes("other_admins", [])
cc.init_attributes("CHATGPT_BASE_URL", "")
cc.init_attributes("qqbot_appid", "")
cc.init_attributes("qqbot_secret", "")
cc.init_attributes("llm_env_prompt", "> hint: 末尾根据内容和心情添加 1-2 个emoji")
cc.init_attributes("default_personality_str", "")
cc.init_attributes("openai_image_generate", {
    "model": "dall-e-3",
    "size": "1024x1024",
    "style": "vivid",
    "quality": "standard",
})
cc.init_attributes("http_proxy", "")
cc.init_attributes("https_proxy", "")
cc.init_attributes("dashboard_username", "")
cc.init_attributes("dashboard_password", "")
# cc.init_attributes(["qq_forward_mode"], False)

# QQ机器人
gocq_bot = None
PLATFORM_GOCQ = 'gocq'
gocq_app = CQHTTP(
    host=cc.get("gocq_host", "127.0.0.1"),
    port=cc.get("gocq_websocket_port", 6700),
    http_port=cc.get("gocq_http_port", 5700),
)
qq_bot: UnofficialQQBotSDK = UnofficialQQBotSDK(
    cc.get("qqbot_appid", None),
    cc.get("qqbot_secret", None)
)

gocq_loop: asyncio.AbstractEventLoop = None
qqbot_loop: asyncio.AbstractEventLoop = None


# 全局对象
_global_object: GlobalObject = None

def new_sub_thread(func, args=()):
    thread = threading.Thread(target=_runner, args=(func, args), daemon=True)
    thread.start()

def _runner(func: Callable, args: tuple):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(func(*args))
    loop.close()

# 统计消息数据
def upload():
    global version, gocq_bot, qqchannel_bot
    while True:
        addr = ''
        addr_ip = ''
        session_dict_dump = '{}'
        try:
            addr = requests.get('http://myip.ipip.net', timeout=5).text
            addr_ip = re.findall(r'\d+.\d+.\d+.\d+', addr)[0]
        except BaseException as e:
            pass
        try:
            gocq_cnt = 0
            qqchan_cnt = 0
            if gocq_bot is not None:
                gocq_cnt = gocq_bot.get_cnt()
            if qqchannel_bot is not None:
                qqchan_cnt = qqchannel_bot.get_cnt()
            o = {"cnt_total": _global_object.cnt_total,"admin": _global_object.admin_qq,"addr": addr, 's': session_dict_dump}
            o_j = json.dumps(o)
            res = {"version": version, "count": gocq_cnt+qqchan_cnt, "ip": addr_ip, "others": o_j, "cntqc": qqchan_cnt, "cntgc": gocq_cnt}
            gu.log(res, gu.LEVEL_DEBUG, tag="Upload", fg = gu.FG_COLORS['yellow'], bg=gu.BG_COLORS['black'])
            resp = requests.post('https://api.soulter.top/upload', data=json.dumps(res), timeout=5)
            # print(resp.text)
            if resp.status_code == 200:
                ok = resp.json()
                if ok['status'] == 'ok':
                    _global_object.cnt_total = 0
                    if gocq_bot is not None:
                        gocq_cnt = gocq_bot.set_cnt(0)
                    if qqchannel_bot is not None:
                        qqchan_cnt = qqchannel_bot.set_cnt(0)
                    
        except BaseException as e:
            gu.log("上传统计信息时出现错误: " + str(e), gu.LEVEL_ERROR, tag="Upload")
            pass
        time.sleep(10*60)


# 语言模型选择
def privider_chooser(cfg):
    l = []
    if 'rev_ChatGPT' in cfg and cfg['rev_ChatGPT']['enable']:
        l.append('rev_chatgpt')
    if 'rev_ernie' in cfg and cfg['rev_ernie']['enable']:
        l.append('rev_ernie')
    if 'rev_edgegpt' in cfg and cfg['rev_edgegpt']['enable']:
        l.append('rev_edgegpt')
    if 'openai' in cfg and len(cfg['openai']['key']) > 0 and cfg['openai']['key'][0] is not None:
        l.append('openai_official')
    return l

'''
初始化机器人
'''
def initBot(cfg):
    global llm_instance, llm_command_instance
    global baidu_judge, chosen_provider
    global frequency_count, frequency_time, announcement, direct_message_mode
    global keywords, _global_object
    
    # 迁移旧配置
    gu.try_migrate_config(cfg)
    # 使用新配置
    cfg = cc.get_all()

    _event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_event_loop)

    # 初始化 global_object
    _global_object = GlobalObject()
    _global_object.base_config = cfg
    _global_object.stat['session'] = {}
    _global_object.stat['message'] = {}
    _global_object.stat['platform'] = {}

    if 'reply_prefix' in cfg:
        # 适配旧版配置
        if isinstance(cfg['reply_prefix'], dict):
            for k in cfg['reply_prefix']:
                _global_object.reply_prefix = cfg['reply_prefix'][k]
                break
        else:
            _global_object.reply_prefix = cfg['reply_prefix']

    # 语言模型提供商
    gu.log("--------加载语言模型--------", gu.LEVEL_INFO, fg=gu.FG_COLORS['yellow'])
    prov = privider_chooser(cfg)
    if REV_CHATGPT in prov:
        gu.log("- 逆向ChatGPT库 -", gu.LEVEL_INFO)
        if cfg['rev_ChatGPT']['enable']:
            if 'account' in cfg['rev_ChatGPT']:
                from model.provider.rev_chatgpt import ProviderRevChatGPT
                from model.command.rev_chatgpt import CommandRevChatGPT
                llm_instance[REV_CHATGPT] = ProviderRevChatGPT(cfg['rev_ChatGPT'], base_url=cc.get("CHATGPT_BASE_URL", None))
                llm_command_instance[REV_CHATGPT] = CommandRevChatGPT(llm_instance[REV_CHATGPT], _global_object)
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
                    from model.provider.rev_edgegpt import ProviderRevEdgeGPT
                    from model.command.rev_edgegpt import CommandRevEdgeGPT
                    llm_instance[REV_EDGEGPT] = ProviderRevEdgeGPT()
                    llm_command_instance[REV_EDGEGPT] = CommandRevEdgeGPT(llm_instance[REV_EDGEGPT], _global_object)
                    chosen_provider = REV_EDGEGPT
                except BaseException as e:
                    print(traceback.format_exc())
                    gu.log("加载Bing模型时发生错误, 请检查1. cookies文件是否正确放置 2. 是否设置了代理（梯子）。", gu.LEVEL_ERROR, max_len=60)
    if OPENAI_OFFICIAL in prov:
        gu.log("- OpenAI官方 -", gu.LEVEL_INFO)
        if cfg['openai']['key'] is not None and cfg['openai']['key'] != [None]:
            from model.provider.openai_official import ProviderOpenAIOfficial
            from model.command.openai_official import CommandOpenAIOfficial
            llm_instance[OPENAI_OFFICIAL] = ProviderOpenAIOfficial(cfg['openai'])
            llm_command_instance[OPENAI_OFFICIAL] = CommandOpenAIOfficial(llm_instance[OPENAI_OFFICIAL], _global_object)
            chosen_provider = OPENAI_OFFICIAL

    gu.log("--------加载配置--------", gu.LEVEL_INFO, fg=gu.FG_COLORS['yellow'])
    # 得到关键词
    if os.path.exists("keyword.json"):
        with open("keyword.json", 'r', encoding='utf-8') as f:
            keywords = json.load(f)

    # 检查provider设置偏好
    p = cc.get("chosen_provider", None)
    if p is not None and p in llm_instance:
        chosen_provider = p
    gu.log(f"将使用 {chosen_provider} 语言模型。", gu.LEVEL_INFO)
    
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
        if cc.get("qq_welcome", None) != None and cfg['notice'] == '此机器人由Github项目QQChannelChatGPT驱动。':
            announcement = cc.get("qq_welcome", None)
        else:
            announcement = cfg['notice']
        gu.log("公告配置: " + announcement, gu.LEVEL_INFO)
    
    try:
        if 'uniqueSessionMode' in cfg and cfg['uniqueSessionMode']:
            _global_object.uniqueSession = True
        else:
            _global_object.uniqueSession = False
        gu.log("独立会话: "+str(_global_object.uniqueSession), gu.LEVEL_INFO)
    except BaseException as e:
        gu.log("独立会话配置错误: "+str(e), gu.LEVEL_ERROR)

    
    gu.log(f"QQ开放平台AppID: {cfg['qqbot']['appid']} 令牌: {cfg['qqbot']['token']}")

    if chosen_provider is None:
        gu.log("检测到没有启动任何语言模型。", gu.LEVEL_CRITICAL)

    nick_qq = cc.get("nick_qq", None)
    if nick_qq == None:
        nick_qq = ("ai","!","！")
    if isinstance(nick_qq, str):
        nick_qq = (nick_qq,)
    if isinstance(nick_qq, list):
        nick_qq = tuple(nick_qq)
    _global_object.nick = nick_qq

    thread_inst = None

    gu.log("--------加载插件--------", gu.LEVEL_INFO, fg=gu.FG_COLORS['yellow'])
    # 加载插件
    _command = Command(None, _global_object)
    ok, err = putil.plugin_reload(_global_object.cached_plugins)
    if ok:
        gu.log("加载插件完成", gu.LEVEL_INFO)
    else:
        gu.log(err, gu.LEVEL_ERROR)
    
    if chosen_provider is None:
        llm_command_instance[NONE_LLM] = _command
        chosen_provider = NONE_LLM

    gu.log("--------加载机器人平台--------", gu.LEVEL_INFO, fg=gu.FG_COLORS['yellow'])

    admin_qq = cc.get('admin_qq', None)
    admin_qqchan = cc.get('admin_qqchan', None)
    if admin_qq == None:
        gu.log("未设置管理者QQ号(管理者才能使用update/plugin等指令)，如需设置，请编辑 cmd_config.json 文件", gu.LEVEL_WARNING)

    if admin_qqchan == None:
        gu.log("未设置管理者QQ频道用户号(管理者才能使用update/plugin等指令)，如需设置，请编辑 cmd_config.json 文件。可在频道发送指令 !myid 获取", gu.LEVEL_WARNING)

    _global_object.admin_qq = admin_qq
    _global_object.admin_qqchan = admin_qqchan

    global qq_bot, qqbot_loop
    qqbot_loop = asyncio.new_event_loop()
    if cc.get("qqbot_appid", '') != '' and cc.get("qqbot_secret", '') != '':
        gu.log("- 启用QQ群机器人 -", gu.LEVEL_INFO)
        thread_inst = threading.Thread(target=run_qqbot, args=(qqbot_loop, qq_bot,), daemon=True)
        thread_inst.start()

    # GOCQ
    global gocq_bot
    if 'gocqbot' in cfg and cfg['gocqbot']['enable']:
        gu.log("- 启用QQ机器人 -", gu.LEVEL_INFO)
        
        global gocq_app, gocq_loop
        gocq_loop = asyncio.new_event_loop()
        gocq_bot = QQ(True, cc, gocq_loop)
        thread_inst = threading.Thread(target=run_gocq_bot, args=(gocq_loop, gocq_bot, gocq_app), daemon=True)
        thread_inst.start()
    else:
        gocq_bot = QQ(False)

    _global_object.platform_qq = gocq_bot

    gu.log("机器人部署教程: https://github.com/Soulter/QQChannelChatGPT/wiki/", gu.LEVEL_INFO, fg=gu.FG_COLORS['yellow'])
    gu.log("如果有任何问题, 请在 https://github.com/Soulter/QQChannelChatGPT 上提交 issue 或加群 322154837", gu.LEVEL_INFO, fg=gu.FG_COLORS['yellow'])
    gu.log("请给 https://github.com/Soulter/QQChannelChatGPT 点个 star!", gu.LEVEL_INFO, fg=gu.FG_COLORS['yellow'])

    # QQ频道
    if 'qqbot' in cfg and cfg['qqbot']['enable']:
        gu.log("- 启用QQ频道机器人 -", gu.LEVEL_INFO)
        global qqchannel_bot, qqchan_loop
        qqchannel_bot = QQChan()
        qqchan_loop = asyncio.new_event_loop()
        _global_object.platform_qqchan = qqchannel_bot
        thread_inst = threading.Thread(target=run_qqchan_bot, args=(cfg, qqchan_loop, qqchannel_bot), daemon=True)
        thread_inst.start()
        # thread.join()

    if thread_inst == None:
        gu.log("没有启用/成功启用任何机器人平台", gu.LEVEL_CRITICAL)

    default_personality_str = cc.get("default_personality_str", "")
    if default_personality_str == "":
        _global_object.default_personality = None
    else: 
        _global_object.default_personality = {
            "name": "default",
            "prompt": default_personality_str,
        }
    # 初始化dashboard
    _global_object.dashboard_data = DashBoardData(
        stats={},
        configs={},
        logs={},
        plugins=_global_object.cached_plugins,
    )
    dashboard_helper = DashBoardHelper(_global_object.dashboard_data, config=cc.get_all())
    dashboard_thread = threading.Thread(target=dashboard_helper.run, daemon=True)
    dashboard_thread.start()

    # 运行 monitor
    threading.Thread(target=run_monitor, args=(_global_object,), daemon=False).start()
        
    gu.log("🎉 项目启动完成。")
    
    # asyncio.get_event_loop().run_until_complete(cli())

    dashboard_thread.join()

async def cli():
    time.sleep(1)
    while True:
        try:
            prompt = input(">>> ")
            if prompt == "":
                continue
            ngm = await cli_pack_message(prompt)
            await oper_msg(ngm, True, PLATFORM_CLI)
        except EOFError:
            return

async def cli_pack_message(prompt: str) -> NakuruGuildMessage:
    ngm = NakuruGuildMessage()
    ngm.channel_id = 6180
    ngm.user_id = 6180
    ngm.message = [Plain(prompt)]
    ngm.type = "GuildMessage"
    ngm.self_id = 6180
    ngm.self_tiny_id = 6180
    ngm.guild_id = 6180
    ngm.sender = NakuruGuildMember()
    ngm.sender.tiny_id = 6180
    ngm.sender.user_id = 6180
    ngm.sender.nickname = "CLI"
    ngm.sender.role = 0
    return ngm

'''
运行QQ频道机器人
'''
def run_qqchan_bot(cfg, loop, qqchannel_bot: QQChan):
    asyncio.set_event_loop(loop)
    intents = botpy.Intents(public_guild_messages=True, direct_message=True) 
    global client
    client = botClient(
        intents=intents,
        bot_log=False
    )
    try:
        qqchannel_bot.run_bot(client, cfg['qqbot']['appid'], cfg['qqbot']['token'])
    except BaseException as e:
        gu.log("启动QQ频道机器人时出现错误, 原因如下: " + str(e), gu.LEVEL_CRITICAL, tag="QQ频道")
        gu.log(r"如果您是初次启动，请修改配置文件（QQChannelChatGPT/config.yaml）详情请看：https://github.com/Soulter/QQChannelChatGPT/wiki。" + str(e), gu.LEVEL_CRITICAL, tag="System")
        
        i = input("按回车退出程序。\n")

'''
运行GOCQ机器人
'''
def run_gocq_bot(loop, gocq_bot, gocq_app):
    asyncio.set_event_loop(loop)
    gu.log("正在检查本地GO-CQHTTP连接...端口5700, 6700", tag="QQ")
    noticed = False
    while True:
        if not gu.port_checker(5700, cc.get("gocq_host", "127.0.0.1")) or not gu.port_checker(6700, cc.get("gocq_host", "127.0.0.1")):
            if not noticed:
                noticed = True
                gu.log("与GO-CQHTTP通信失败, 请检查GO-CQHTTP是否启动并正确配置。程序会每隔 5s 自动重试。", gu.LEVEL_CRITICAL, tag="QQ")
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
启动QQ群机器人(官方接口)
'''
def run_qqbot(loop: asyncio.AbstractEventLoop, qq_bot: UnofficialQQBotSDK):
    asyncio.set_event_loop(loop)
    QQBotClient()
    qq_bot.run_bot()


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


'''
通用消息回复
'''
async def send_message(platform, message, res, session_id = None):
    global qqchannel_bot, qqchannel_bot, gocq_loop, session_dict

    # 统计会话信息
    if session_id is not None:
        if session_id not in session_dict:
            session_dict[session_id] = {'cnt': 1}
        else:
            session_dict[session_id]['cnt'] += 1
    else:
        session_dict[session_id]['cnt'] += 1

    # TODO: 这里会非常吃资源。然而 sqlite3 不支持多线程，所以暂时这样写。
    curr_ts = int(time.time())
    db_inst = dbConn()
    db_inst.increment_stat_session(platform, session_id, 1)
    db_inst.increment_stat_message(curr_ts, 1)
    db_inst.increment_stat_platform(curr_ts, platform, 1)

    if platform == PLATFORM_QQCHAN:
        qqchannel_bot.send_qq_msg(message, res)
    elif platform == PLATFORM_GOCQ:
        await gocq_bot.send_qq_msg(message, res)
    elif platform == PLATFROM_QQBOT:
        message_chain = MessageChain()
        message_chain.parse_from_nakuru(res)
        await qq_bot.send(message, message_chain)
    elif platform == PLATFORM_CLI:
        print(res)

async def oper_msg(message: Union[GroupMessage, FriendMessage, GuildMessage, NakuruGuildMessage],
             group: bool=False,
             platform: str = None):
    """
    处理消息。
    group: 群聊模式,
    message: 频道是频道的消息对象, QQ是nakuru-gocq的消息对象
    msg_ref: 引用消息（频道）
    platform: 平台(gocq, qqchan)
    """
    global chosen_provider, keywords, qqchannel_bot, gocq_bot
    global _global_object
    qq_msg = ''
    session_id = ''
    user_id = ''
    role = "member" # 角色, member或admin
    hit = False # 是否命中指令
    command_result = () # 调用指令返回的结果
    
    _global_object.cnt_total += 1

    with_tag = False # 是否带有昵称

    if platform == PLATFORM_QQCHAN or platform == PLATFROM_QQBOT or platform == PLATFORM_CLI:
        with_tag = True

    _len = 0
    for i in message.message:
        if isinstance(i, Plain) or isinstance(i, PlainText):
            qq_msg += str(i.text).strip()
        if isinstance(i, At):
            if message.type == "GuildMessage":
                if i.qq == message.user_id or i.qq == message.self_tiny_id:
                    with_tag = True
            if message.type == "FriendMessage":
                if i.qq == message.self_id:
                    with_tag = True
            if message.type == "GroupMessage":
                if i.qq == message.self_id:
                    with_tag = True
        
    for i in _global_object.nick:
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
        session_id = message.user_id

    if message.type == "GuildMessage":
        sender_id = str(message.sender.tiny_id)
    else:
        sender_id = str(message.sender.user_id)
    if sender_id == _global_object.admin_qq or \
        sender_id == _global_object.admin_qqchan or \
        sender_id in cc.get("other_admins", []) or \
        sender_id == cc.get("gocq_qqchan_admin", "") or \
        platform == PLATFORM_CLI:
        role = "admin"

    if _global_object.uniqueSession:
        # 独立会话时，一个用户一个 session
        session_id = sender_id


    if qq_msg == "":
        await send_message(platform, message,  f"Hi~", session_id=session_id)
        return
    
    if with_tag:
        # 检查发言频率
        if not check_frequency(user_id):
            await send_message(platform, message, f'你的发言超过频率限制(╯▔皿▔)╯。\n管理员设置{frequency_time}秒内只能提问{frequency_count}次。', session_id=session_id)
            return

    # logf.write("[GOCQBOT] "+ qq_msg+'\n')
    # logf.flush()

    # 关键词回复
    for k in keywords:
        if qq_msg == k:
            plain_text = ""
            if 'plain_text' in keywords[k]:
                plain_text = keywords[k]['plain_text']
            else:
                plain_text = keywords[k]
            image_url = ""
            if 'image_url' in keywords[k]:
                image_url = keywords[k]['image_url']
            if image_url != "":
                res = [Plain(plain_text), Image.fromURL(image_url)]
                await send_message(platform, message, res, session_id=session_id)
            else:
                await send_message(platform, message, plain_text, session_id=session_id)
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
            chosen_provider = target
            cc.put("chosen_provider", chosen_provider)
            await send_message(platform, message, f"已切换至【{chosen_provider}】", session_id=session_id)
            return
        
    chatgpt_res = ""

    # 如果是等待回复的消息
    if platform == PLATFORM_GOCQ and session_id in gocq_bot.waiting and gocq_bot.waiting[session_id] == '':
        gocq_bot.waiting[session_id] = message
        return
    if platform == PLATFORM_QQCHAN and session_id in qqchannel_bot.waiting and qqchannel_bot.waiting[session_id] == '':
        qqchannel_bot.waiting[session_id] = message
        return

    hit, command_result = llm_command_instance[chosen_provider].check_command(
        qq_msg,
        session_id,
        role,
        platform,
        message,
    )

    # 没触发指令
    if not hit:
        if not with_tag:
            return
        # 关键词拦截
        for i in uw.unfit_words_q:
            matches = re.match(i, qq_msg.strip(), re.I | re.M)
            if matches:
                await send_message(platform, message,  f"你的提问得到的回复未通过【自有关键词拦截】服务, 不予回复。", session_id=session_id)
                return
        if baidu_judge != None:
            check, msg = baidu_judge.judge(qq_msg)
            if not check:
                await send_message(platform, message,  f"你的提问得到的回复未通过【百度AI内容审核】服务, 不予回复。\n\n{msg}", session_id=session_id)
                return
        if chosen_provider == None:
            await send_message(platform, message, f"管理员未启动任何语言模型或者语言模型初始化时失败。", session_id=session_id)
            return
        try:
            # check image url
            image_url = None
            for comp in message.message:
                if isinstance(comp, Image):
                    if comp.url is None:
                        image_url = comp.file
                        break
                    else:
                        image_url = comp.url
                        break
            # web search keyword
            web_sch_flag = False
            if qq_msg.startswith("ws ") and qq_msg != "ws ":
                qq_msg = qq_msg[3:]
                web_sch_flag = True
            else:
                qq_msg += " " + cc.get("llm_env_prompt", "")
            if chosen_provider == REV_CHATGPT or chosen_provider == OPENAI_OFFICIAL:
                if _global_object.web_search or web_sch_flag:
                    official_fc = chosen_provider == OPENAI_OFFICIAL
                    chatgpt_res = gplugin.web_search(qq_msg, llm_instance[chosen_provider], session_id, official_fc)
                else:
                    chatgpt_res = str(llm_instance[chosen_provider].text_chat(qq_msg, session_id, image_url, default_personality = _global_object.default_personality))
            elif chosen_provider == REV_EDGEGPT:
                res, res_code = await llm_instance[chosen_provider].text_chat(qq_msg, platform)
                if res_code == 0: # bing不想继续话题，重置会话后重试。
                    await send_message(platform, message, "Bing不想继续话题了, 正在自动重置会话并重试。", session_id=session_id)
                    await llm_instance[chosen_provider].forget()
                    res, res_code = await llm_instance[chosen_provider].text_chat(qq_msg, platform)
                    if res_code == 0: # bing还是不想继续话题，大概率说明提问有问题。
                        await llm_instance[chosen_provider].forget()
                        await send_message(platform, message, "Bing仍然不想继续话题, 会话已重置, 请检查您的提问后重试。", session_id=session_id)
                        res = ""
                chatgpt_res = str(res)

            chatgpt_res = _global_object.reply_prefix + chatgpt_res
        except BaseException as e:
            gu.log(f"调用异常：{traceback.format_exc()}", gu.LEVEL_ERROR, max_len=100000)
            gu.log("调用语言模型例程时出现异常。原因: "+str(e), gu.LEVEL_ERROR)
            await send_message(platform, message, "调用语言模型例程时出现异常。原因: "+str(e), session_id=session_id)
            return

    # 切换回原来的语言模型
    if temp_switch != "":
        chosen_provider = temp_switch
        
    # 指令回复
    if hit:
        # 检查指令. command_result是一个元组：(指令调用是否成功, 指令返回的文本结果, 指令类型)
        if command_result == None:
            return

        command = command_result[2]
        if command == "keyword":
            if os.path.exists("keyword.json"):
                with open("keyword.json", "r", encoding="utf-8") as f:
                    keywords = json.load(f)
            else:
                try:
                    await send_message(platform, message, command_result[1], session_id=session_id)
                except BaseException as e:
                    await send_message(platform, message, f"回复消息出错: {str(e)}", session_id=session_id)

        if command == "update latest r":
            await send_message(platform, message, command_result[1] + "\n\n即将自动重启。", session_id=session_id)
            py = sys.executable
            os.execl(py, py, *sys.argv)

        if not command_result[0]:
            await send_message(platform, message, f"指令调用错误: \n{str(command_result[1])}", session_id=session_id)
            return
        
        # 画图指令
        if isinstance(command_result[1], list) and len(command_result) == 3 and command == 'draw':
            for i in command_result[1]:
                # i is a link
                # 保存到本地
                pic_res = requests.get(i, stream = True)
                if pic_res.status_code == 200:
                    image = PILImage.open(io.BytesIO(pic_res.content))
                    await send_message(platform, message, [Image.fromFileSystem(gu.save_temp_img(image))], session_id=session_id)
        
        # 其他指令
        else:
            try:
                await send_message(platform, message, command_result[1], session_id=session_id)
            except BaseException as e:
                await send_message(platform, message, f"回复消息出错: {str(e)}", session_id=session_id)

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
            await send_message(platform, message, f"你的提问得到的回复【百度内容审核】未通过，不予回复。\n\n{msg}", session_id=session_id)
            return
        
    # 发送信息
    try:
        await send_message(platform, message, chatgpt_res, session_id=session_id)
    except BaseException as e:
        gu.log("回复消息错误: \n"+str(e), gu.LEVEL_ERROR)

# QQ频道机器人
class botClient(botpy.Client):
    # 收到频道消息
    async def on_at_message_create(self, message: Message):
        gu.log(str(message), gu.LEVEL_DEBUG, max_len=9999)

        # 转换层
        nakuru_guild_message = qqchannel_bot.gocq_compatible_receive(message)
        gu.log(f"转换后: {str(nakuru_guild_message)}", gu.LEVEL_DEBUG, max_len=9999)
        new_sub_thread(oper_msg, (nakuru_guild_message, True, PLATFORM_QQCHAN))

    # 收到私聊消息
    async def on_direct_message_create(self, message: DirectMessage):
        if direct_message_mode:

            # 转换层
            nakuru_guild_message = qqchannel_bot.gocq_compatible_receive(message)
            gu.log(f"转换后: {str(nakuru_guild_message)}", gu.LEVEL_DEBUG, max_len=9999)

            new_sub_thread(oper_msg, (nakuru_guild_message, False, PLATFORM_QQCHAN))
# QQ机器人
class gocqClient():
    # 收到群聊消息
    @gocq_app.receiver("GroupMessage")
    async def _(app: CQHTTP, source: GroupMessage):
        if cc.get("gocq_react_group", True):
            if isinstance(source.message[0], Plain):
                new_sub_thread(oper_msg, (source, True, PLATFORM_GOCQ))
            if isinstance(source.message[0], At):
                if source.message[0].qq == source.self_id:
                    new_sub_thread(oper_msg, (source, True, PLATFORM_GOCQ))
            else:
                return
        
    @gocq_app.receiver("FriendMessage")
    async def _(app: CQHTTP, source: FriendMessage):
        if cc.get("gocq_react_friend", True):
            if isinstance(source.message[0], Plain):
                new_sub_thread(oper_msg, (source, False, PLATFORM_GOCQ))
            else:
                return
        
    @gocq_app.receiver("GroupMemberIncrease")
    async def _(app: CQHTTP, source: GroupMemberIncrease):
        if cc.get("gocq_react_group_increase", True):
            global announcement
            await app.sendGroupMessage(source.group_id, [
                Plain(text = announcement),
            ])

    @gocq_app.receiver("Notify")
    async def _(app: CQHTTP, source: Notify):
        print(source)
        if source.sub_type == "poke" and source.target_id == source.self_id:
            new_sub_thread(oper_msg, (source, False, PLATFORM_GOCQ))

    @gocq_app.receiver("GuildMessage")
    async def _(app: CQHTTP, source: GuildMessage):
        if cc.get("gocq_react_guild", True):
            if isinstance(source.message[0], Plain):
                new_sub_thread(oper_msg, (source, True, PLATFORM_GOCQ))
            if isinstance(source.message[0], At):
                if source.message[0].qq == source.self_tiny_id:
                    new_sub_thread(oper_msg, (source, True, PLATFORM_GOCQ))
            else:
                return
            
class QQBotClient():
    @qq_bot.on('GroupMessage')
    async def _(bot: UnofficialQQBotSDK, message: QQMessage):
        print(message)
        new_sub_thread(oper_msg, (message, True, PLATFROM_QQBOT))