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
from nakuru import (
    GroupMessage,
    FriendMessage,
    GuildMessage,
)
from model.platform._nakuru_translation_layer import NakuruGuildMember, NakuruGuildMessage
from nakuru.entities.components import Plain,At,Image
from model.provider.provider import Provider
from model.command.command import Command
from util import general_utils as gu
from util.cmd_config import CmdConfig as cc
from util.cmd_config import init_astrbot_config_items
import util.function_calling.gplugin as gplugin
import util.plugin_util as putil
from PIL import Image as PILImage
import io
import traceback
from . global_object import GlobalObject
from typing import Union
from addons.dashboard.helper import DashBoardHelper
from addons.dashboard.server import DashBoardData
from cores.monitor.perf import run_monitor
from cores.database.conn import dbConn
from model.platform._message_result import MessageResult

# 用户发言频率
user_frequency = {}
# 时间默认值
frequency_time = 60
# 计数默认值
frequency_count = 2

# 版本
version = '3.1.1'

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

# CLI
PLATFORM_CLI = 'cli'

init_astrbot_config_items()

# 全局对象
_global_object: GlobalObject = None

# 统计消息数据
def upload():
    global version
    while True:
        addr_ip = ''
        try:

            o = {
                "cnt_total": _global_object.cnt_total,
                "admin": _global_object.admin_qq, 
            }
            o_j = json.dumps(o)
            res = {
                "version": version, 
                "count": _global_object.cnt_total,
                "cntqc": -1,
                "cntgc": -1,
                "ip": addr_ip,
                "others": o_j,
                "sys": sys.platform,
            }
            gu.log(res, gu.LEVEL_DEBUG, tag="Upload", fg = gu.FG_COLORS['yellow'], bg=gu.BG_COLORS['black'])
            resp = requests.post('https://api.soulter.top/upload', data=json.dumps(res), timeout=5)
            if resp.status_code == 200:
                ok = resp.json()
                if ok['status'] == 'ok':
                    _global_object.cnt_total = 0
                    
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
    global frequency_count, frequency_time
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
        gu.log("私聊功能: "+str(cfg['direct_message_mode']), gu.LEVEL_INFO)

    # 得到发言频率配置
    if 'limit' in cfg:
        gu.log("发言频率配置: "+str(cfg['limit']), gu.LEVEL_INFO)
        if 'count' in cfg['limit']:
            frequency_count = cfg['limit']['count']
        if 'time' in cfg['limit']:
            frequency_time = cfg['limit']['time']
    
    try:
        if 'uniqueSessionMode' in cfg and cfg['uniqueSessionMode']:
            _global_object.uniqueSession = True
        else:
            _global_object.uniqueSession = False
        gu.log("独立会话: "+str(_global_object.uniqueSession), gu.LEVEL_INFO)
    except BaseException as e:
        gu.log("独立会话配置错误: "+str(e), gu.LEVEL_ERROR)

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

    gu.log("提示：需要添加管理员 ID 才能使用 update/plugin 等指令)，可在可视化面板添加。（如已添加可忽略）", gu.LEVEL_WARNING)

    # GOCQ
    if 'gocqbot' in cfg and cfg['gocqbot']['enable']:
        gu.log("- 启用 QQ_GOCQ 机器人 -", gu.LEVEL_INFO)
        threading.Thread(target=run_gocq_bot, args=(cfg, _global_object), daemon=True).start()

    # QQ频道
    if 'qqbot' in cfg and cfg['qqbot']['enable']:
        gu.log("- 启用 QQ_OFFICIAL 机器人 -", gu.LEVEL_INFO)
        threading.Thread(target=run_qqchan_bot, args=(cfg, _global_object), daemon=True).start()

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

    gu.log("如果有任何问题, 请在 https://github.com/Soulter/AstrBot 上提交 issue 或加群 322154837。", gu.LEVEL_INFO, fg=gu.FG_COLORS['yellow'])
    gu.log("请给 https://github.com/Soulter/AstrBot 点个 star。", gu.LEVEL_INFO, fg=gu.FG_COLORS['yellow'])
    gu.log("🎉 项目启动完成。")
    
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
运行 QQ_OFFICIAL 机器人
'''
def run_qqchan_bot(cfg: dict, global_object: GlobalObject):
    try:
        from model.platform.qq_official import QQOfficial
        qqchannel_bot = QQOfficial(cfg=cfg, message_handler=oper_msg)
        global_object.platform_qqchan = qqchannel_bot
        qqchannel_bot.run()
    except BaseException as e:
        gu.log("启动QQ频道机器人时出现错误, 原因如下: " + str(e), gu.LEVEL_CRITICAL, tag="QQ频道")
        gu.log(r"如果您是初次启动，请前往可视化面板填写配置。详情请看：https://astrbot.soulter.top/center/。" + str(e), gu.LEVEL_CRITICAL, tag="System")

'''
运行 QQ_GOCQ 机器人
'''
def run_gocq_bot(cfg: dict, _global_object: GlobalObject):
    from model.platform.qq_gocq import QQGOCQ
    
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
    try:
        qq_gocq = QQGOCQ(cfg=cfg, message_handler=oper_msg)
        _global_object.platform_qq = qq_gocq
        qq_gocq.run()
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

async def record_message(platform: str, session_id: str):
    # TODO: 这里会非常吃资源。然而 sqlite3 不支持多线程，所以暂时这样写。
    curr_ts = int(time.time())
    db_inst = dbConn()
    db_inst.increment_stat_session(platform, session_id, 1)
    db_inst.increment_stat_message(curr_ts, 1)
    db_inst.increment_stat_platform(curr_ts, platform, 1)
    _global_object.cnt_total += 1

async def oper_msg(message: Union[GroupMessage, FriendMessage, GuildMessage, NakuruGuildMessage],
             session_id: str,
             role: str = 'member',
             platform: str = None,
) -> MessageResult:
    """
    处理消息。
    message: 消息对象
    session_id: 该消息源的唯一识别号
    role: member | admin
    platform: 平台(gocq, qqchan)
    """
    global chosen_provider, keywords
    global _global_object
    message_str = ''
    session_id = session_id
    role = role
    hit = False # 是否命中指令
    command_result = () # 调用指令返回的结果
    message_result = None # 消息返回结果

    record_message(platform, session_id)

    for i in message.message:
        if isinstance(i, Plain):
            message_str += i.text.strip()
    gu.log(f"收到消息：{message_str}", gu.LEVEL_INFO, tag=platform)
    if message_str == "":
        return MessageResult("Hi~")
    
    # 检查发言频率
    user_id = message.user_id
    if not check_frequency(user_id):
        return MessageResult(f'你的发言超过频率限制(╯▔皿▔)╯。\n管理员设置{frequency_time}秒内只能提问{frequency_count}次。')

    # 关键词回复
    for k in keywords:
        if message_str == k:
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
                return MessageResult(res)
            return MessageResult(plain_text)
    
    # 检查是否是更换语言模型的请求
    temp_switch = ""
    if message_str.startswith('/bing') or message_str.startswith('/gpt') or message_str.startswith('/revgpt'):
        target = chosen_provider
        if message_str.startswith('/bing'):
            target = REV_EDGEGPT
        elif message_str.startswith('/gpt'):
            target = OPENAI_OFFICIAL
        elif message_str.startswith('/revgpt'):
            target = REV_CHATGPT
        l = message_str.split(' ')
        if len(l) > 1 and l[1] != "":
            # 临时对话模式，先记录下之前的语言模型，回答完毕后再切回
            temp_switch = chosen_provider
            chosen_provider = target
            message_str = l[1]
        else:
            chosen_provider = target
            cc.put("chosen_provider", chosen_provider)
            return MessageResult(f"已切换至【{chosen_provider}】")

    llm_result_str = ""

    hit, command_result = llm_command_instance[chosen_provider].check_command(
        message_str,
        session_id,
        role,
        platform,
        message,
    )

    # 没触发指令
    if not hit:
        # 关键词拦截
        for i in uw.unfit_words_q:
            matches = re.match(i, message_str.strip(), re.I | re.M)
            if matches:
                return MessageResult(f"你的提问得到的回复未通过【自有关键词拦截】服务, 不予回复。")
        if baidu_judge != None:
            check, msg = baidu_judge.judge(message_str)
            if not check:
                return MessageResult(f"你的提问得到的回复未通过【百度AI内容审核】服务, 不予回复。\n\n{msg}")
        if chosen_provider == None:
            return MessageResult(f"管理员未启动任何语言模型或者语言模型初始化时失败。")
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
            if message_str.startswith("ws ") and message_str != "ws ":
                message_str = message_str[3:]
                web_sch_flag = True
            else:
                message_str += " " + cc.get("llm_env_prompt", "")
            if chosen_provider == REV_CHATGPT or chosen_provider == OPENAI_OFFICIAL:
                if _global_object.web_search or web_sch_flag:
                    official_fc = chosen_provider == OPENAI_OFFICIAL
                    llm_result_str = gplugin.web_search(message_str, llm_instance[chosen_provider], session_id, official_fc)
                else:
                    llm_result_str = str(llm_instance[chosen_provider].text_chat(message_str, session_id, image_url, default_personality = _global_object.default_personality))
            elif chosen_provider == REV_EDGEGPT:
                return MessageResult("AstrBot 不再默认支持 NewBing 模型。")

            llm_result_str = _global_object.reply_prefix + llm_result_str
        except BaseException as e:
            gu.log(f"调用异常：{traceback.format_exc()}", gu.LEVEL_ERROR, max_len=100000)
            return MessageResult(f"调用语言模型例程时出现异常。原因: {str(e)}")

    # 切换回原来的语言模型
    if temp_switch != "":
        chosen_provider = temp_switch
        
    # 指令回复
    if hit:
        # 检查指令。 command_result 是一个元组：(指令调用是否成功, 指令返回的文本结果, 指令类型)
        if command_result == None:
            return
        command = command_result[2]

        if command == "keyword":
            if os.path.exists("keyword.json"):
                with open("keyword.json", "r", encoding="utf-8") as f:
                    keywords = json.load(f)
            else:
                try:
                    return MessageResult(command_result[1])
                except BaseException as e:
                    return MessageResult(f"回复消息出错: {str(e)}")

        if command == "update latest r":
            def update_restart():
                py = sys.executable
                os.execl(py, py, *sys.argv)
            return MessageResult(command_result[1] + "\n\n即将自动重启。", callback=update_restart)

        if not command_result[0]:
            return MessageResult(f"指令调用错误: \n{str(command_result[1])}")
        
        # 画图指令
        if isinstance(command_result[1], list) and len(command_result) == 3 and command == 'draw':
            for i in command_result[1]:
                # 保存到本地
                pic_res = requests.get(i, stream = True)
                if pic_res.status_code == 200:
                    image = PILImage.open(io.BytesIO(pic_res.content))
                    return MessageResult([Image.fromFileSystem(gu.save_temp_img(image))])
        
        # 其他指令
        else:
            try:
                return MessageResult(command_result[1])
            except BaseException as e:
                return MessageResult(f"回复消息出错: {str(e)}")
        return

    # 敏感过滤
    # 过滤不合适的词
    for i in uw.unfit_words:
        llm_result_str = re.sub(i, "***", llm_result_str)
    # 百度内容审核服务二次审核
    if baidu_judge != None:
        check, msg = baidu_judge.judge(llm_result_str)
        if not check:
            return MessageResult(f"你的提问得到的回复【百度内容审核】未通过，不予回复。\n\n{msg}")
    # 发送信息
    try:
        return MessageResult(llm_result_str)
    except BaseException as e:
        gu.log("回复消息错误: \n"+str(e), gu.LEVEL_ERROR)