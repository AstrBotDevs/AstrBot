import re
import threading
import asyncio
import time
import aiohttp
import util.unfit_words as uw
import os
import sys
import io
import traceback

import util.function_calling.gplugin as gplugin
import util.plugin_util as putil

from PIL import Image as PILImage
from nakuru.entities.components import Plain, At, Image

from addons.baidu_aip_judge import BaiduJudge
from model.provider.provider import Provider
from model.command.command import Command
from util import general_utils as gu
from util.general_utils import upload, run_monitor
from util.cmd_config import CmdConfig as cc
from util.cmd_config import init_astrbot_config_items
from .types import *
from addons.dashboard.helper import DashBoardHelper
from addons.dashboard.server import DashBoardData
from cores.database.conn import dbConn
from model.platform._message_result import MessageResult
from SparkleLogging.utils.core import LogManager
from logging import Logger

logger: Logger = LogManager.GetLogger(log_name='astrbot-core')

# 用户发言频率
user_frequency = {}
# 时间默认值
frequency_time = 60
# 计数默认值
frequency_count = 10

# 版本
version = '3.1.13'

# 语言模型
OPENAI_OFFICIAL = 'openai_official'
NONE_LLM = 'none_llm'
chosen_provider = None
# 语言模型对象
llm_instance: dict[str, Provider] = {}
llm_command_instance: dict[str, Command] = {}
llm_wake_prefix = ""

# 百度内容审核实例
baidu_judge = None

# CLI
PLATFORM_CLI = 'cli'

init_astrbot_config_items()

# 全局对象
_global_object: GlobalObject = None

# 语言模型选择


def privider_chooser(cfg):
    l = []
    if 'openai' in cfg and len(cfg['openai']['key']) > 0 and cfg['openai']['key'][0] is not None:
        l.append('openai_official')
    return l


'''
初始化机器人
'''


def init(cfg):
    global llm_instance, llm_command_instance
    global baidu_judge, chosen_provider
    global frequency_count, frequency_time
    global _global_object

    # 迁移旧配置
    gu.try_migrate_config(cfg)
    # 使用新配置
    cfg = cc.get_all()

    _event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_event_loop)

    # 初始化 global_object
    _global_object = GlobalObject()
    _global_object.version = version
    _global_object.base_config = cfg
    logger.info("AstrBot v"+version)

    if 'reply_prefix' in cfg:
        # 适配旧版配置
        if isinstance(cfg['reply_prefix'], dict):
            _global_object.reply_prefix = ""
            cfg['reply_prefix'] = ""
            cc.put("reply_prefix", "")
        else:
            _global_object.reply_prefix = cfg['reply_prefix']

    # 语言模型提供商
    logger.info("正在载入语言模型...")
    prov = privider_chooser(cfg)
    if OPENAI_OFFICIAL in prov:
        logger.info("初始化：OpenAI官方")
        if cfg['openai']['key'] is not None and cfg['openai']['key'] != [None]:
            from model.provider.openai_official import ProviderOpenAIOfficial
            from model.command.openai_official import CommandOpenAIOfficial
            llm_instance[OPENAI_OFFICIAL] = ProviderOpenAIOfficial(
                cfg['openai'])
            llm_command_instance[OPENAI_OFFICIAL] = CommandOpenAIOfficial(
                llm_instance[OPENAI_OFFICIAL], _global_object)
            _global_object.llms.append(RegisteredLLM(
                llm_name=OPENAI_OFFICIAL, llm_instance=llm_instance[OPENAI_OFFICIAL], origin="internal"))
            chosen_provider = OPENAI_OFFICIAL

    # 检查provider设置偏好
    p = cc.get("chosen_provider", None)
    if p is not None and p in llm_instance:
        chosen_provider = p

    # 百度内容审核
    if 'baidu_aip' in cfg and 'enable' in cfg['baidu_aip'] and cfg['baidu_aip']['enable']:
        try:
            baidu_judge = BaiduJudge(cfg['baidu_aip'])
            logger.info("百度内容审核初始化成功")
        except BaseException as e:
            logger.info("百度内容审核初始化失败")

    threading.Thread(target=upload, args=(
        _global_object, ), daemon=True).start()

    # 得到发言频率配置
    if 'limit' in cfg:
        if 'count' in cfg['limit']:
            frequency_count = cfg['limit']['count']
        if 'time' in cfg['limit']:
            frequency_time = cfg['limit']['time']

    try:
        if 'uniqueSessionMode' in cfg and cfg['uniqueSessionMode']:
            _global_object.unique_session = True
        else:
            _global_object.unique_session = False
    except BaseException as e:
        logger.info("独立会话配置错误: "+str(e))

    nick_qq = cc.get("nick_qq", None)
    if nick_qq == None:
        nick_qq = ("ai", "!", "！")
    if isinstance(nick_qq, str):
        nick_qq = (nick_qq,)
    if isinstance(nick_qq, list):
        nick_qq = tuple(nick_qq)
    _global_object.nick = nick_qq

    # 语言模型唤醒词
    global llm_wake_prefix
    llm_wake_prefix = cc.get("llm_wake_prefix", "")

    logger.info("正在载入插件...")
    # 加载插件
    _command = Command(None, _global_object)
    ok, err = putil.plugin_reload(_global_object.cached_plugins)
    if ok:
        logger.info(
            f"成功载入 {len(_global_object.cached_plugins)} 个插件")
    else:
        logger.info(err)

    if chosen_provider is None:
        llm_command_instance[NONE_LLM] = _command
        chosen_provider = NONE_LLM

    logger.info("正在载入机器人消息平台")
    # logger.info("提示：需要添加管理员 ID 才能使用 update/plugin 等指令)，可在可视化面板添加。（如已添加可忽略）")
    platform_str = ""
    # GOCQ
    if 'gocqbot' in cfg and cfg['gocqbot']['enable']:
        logger.info("启用 QQ_GOCQ 机器人消息平台")
        threading.Thread(target=run_gocq_bot, args=(
            cfg, _global_object), daemon=True).start()
        platform_str += "QQ_GOCQ,"

    # QQ频道
    if 'qqbot' in cfg and cfg['qqbot']['enable'] and cfg['qqbot']['appid'] != None:
        logger.info("启用 QQ_OFFICIAL 机器人消息平台")
        threading.Thread(target=run_qqchan_bot, args=(
            cfg, _global_object), daemon=True).start()
        platform_str += "QQ_OFFICIAL,"

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
    dashboard_helper = DashBoardHelper(_global_object, config=cc.get_all())
    dashboard_thread = threading.Thread(
        target=dashboard_helper.run, daemon=True)
    dashboard_thread.start()

    # 运行 monitor
    threading.Thread(target=run_monitor, args=(
        _global_object,), daemon=True).start()

    logger.info(
        "如果有任何问题, 请在 https://github.com/Soulter/AstrBot 上提交 issue 或加群 322154837。")
    logger.info("请给 https://github.com/Soulter/AstrBot 点个 star。")
    if platform_str == '':
        platform_str = "(未启动任何平台，请前往面板添加)"
    logger.info(f"🎉 项目启动完成")

    dashboard_thread.join()


'''
运行 QQ_OFFICIAL 机器人
'''


def run_qqchan_bot(cfg: dict, global_object: GlobalObject):
    try:
        from model.platform.qq_official import QQOfficial
        qqchannel_bot = QQOfficial(
            cfg=cfg, message_handler=oper_msg, global_object=global_object)
        global_object.platforms.append(RegisteredPlatform(
            platform_name="qqchan", platform_instance=qqchannel_bot, origin="internal"))
        qqchannel_bot.run()
    except BaseException as e:
        logger.error("启动 QQ 频道机器人时出现错误, 原因如下: " + str(e))
        logger.error(r"如果您是初次启动，请前往可视化面板填写配置。详情请看：https://astrbot.soulter.top/center/。")


'''
运行 QQ_GOCQ 机器人
'''


def run_gocq_bot(cfg: dict, _global_object: GlobalObject):
    from model.platform.qq_gocq import QQGOCQ

    noticed = False
    host = cc.get("gocq_host", "127.0.0.1")
    port = cc.get("gocq_websocket_port", 6700)
    http_port = cc.get("gocq_http_port", 5700)
    logger.info(
        f"正在检查连接...host: {host}, ws port: {port}, http port: {http_port}", tag="QQ")
    while True:
        if not gu.port_checker(port=port, host=host) or not gu.port_checker(port=http_port, host=host):
            if not noticed:
                noticed = True
                logger.info(
                    f"连接到{host}:{port}（或{http_port}）失败。程序会每隔 5s 自动重试。", gu.LEVEL_CRITICAL, tag="QQ")
            time.sleep(5)
        else:
            logger.info("检查完毕，未发现问题。", tag="QQ")
            break
    try:
        qq_gocq = QQGOCQ(cfg=cfg, message_handler=oper_msg,
                         global_object=_global_object)
        _global_object.platforms.append(RegisteredPlatform(
            platform_name="gocq", platform_instance=qq_gocq, origin="internal"))
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
                user_frequency[id]['count'] += 1
                return True
    else:
        t = {'time': ts, 'count': 1}
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


async def oper_msg(message: AstrBotMessage,
                   session_id: str,
                   role: str = 'member',
                   platform: str = None,
                   ) -> MessageResult:
    """
    处理消息。
    message: 消息对象
    session_id: 该消息源的唯一识别号
    role: member | admin
    platform: str 所注册的平台的名称。如果没有注册，将抛出一个异常。
    """
    global chosen_provider, _global_object
    message_str = ''
    session_id = session_id
    role = role
    hit = False  # 是否命中指令
    command_result = ()  # 调用指令返回的结果

    # 获取平台实例
    reg_platform: RegisteredPlatform = None
    for p in _global_object.platforms:
        if p.platform_name == platform:
            reg_platform = p
            break
    if not reg_platform:
        raise Exception(f"未找到平台 {platform} 的实例。")

    # 统计数据，如频道消息量
    await record_message(platform, session_id)

    for i in message.message:
        if isinstance(i, Plain):
            message_str += i.text.strip()
    if message_str == "":
        return MessageResult("Hi~")

    # 检查发言频率
    if not check_frequency(message.sender.user_id):
        return MessageResult(f'你的发言超过频率限制(╯▔皿▔)╯。\n管理员设置{frequency_time}秒内只能提问{frequency_count}次。')

    # 检查是否是更换语言模型的请求
    temp_switch = ""
    if message_str.startswith('/gpt'):
        target = chosen_provider
        if message_str.startswith('/gpt'):
            target = OPENAI_OFFICIAL
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

    # check commands and plugins
    hit, command_result = await llm_command_instance[chosen_provider].check_command(
        message_str,
        session_id,
        role,
        reg_platform,
        message,
    )

    # 没触发指令
    if not hit:
        # 关键词拦截
        for i in uw.unfit_words_q:
            matches = re.match(i, message_str.strip(), re.I | re.M)
            if matches:
                return MessageResult(f"你的提问得到的回复未通过【默认关键词拦截】服务, 不予回复。")
        if baidu_judge != None:
            check, msg = await asyncio.to_thread(baidu_judge.judge, message_str)
            if not check:
                return MessageResult(f"你的提问得到的回复未通过【百度AI内容审核】服务, 不予回复。\n\n{msg}")
        if chosen_provider == NONE_LLM:
            logger.info("一条消息由于 Bot 未启动任何语言模型并且未触发指令而将被忽略。")
            return
        try:
            if llm_wake_prefix != "" and not message_str.startswith(llm_wake_prefix):
                return
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
            if chosen_provider == OPENAI_OFFICIAL:
                if _global_object.web_search or web_sch_flag:
                    official_fc = chosen_provider == OPENAI_OFFICIAL
                    llm_result_str = await gplugin.web_search(message_str, llm_instance[chosen_provider], session_id, official_fc)
                else:
                    llm_result_str = await llm_instance[chosen_provider].text_chat(message_str, session_id, image_url, default_personality=_global_object.default_personality)

            llm_result_str = _global_object.reply_prefix + llm_result_str
        except BaseException as e:
            logger.info(f"调用异常：{traceback.format_exc()}")
            return MessageResult(f"调用语言模型例程时出现异常。原因: {str(e)}")

    # 切换回原来的语言模型
    if temp_switch != "":
        chosen_provider = temp_switch

    if hit:
        # 有指令或者插件触发
        # command_result 是一个元组：(指令调用是否成功, 指令返回的文本结果, 指令类型)
        if command_result == None:
            return
        command = command_result[2]

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
                async with aiohttp.ClientSession() as session:
                    async with session.get(i) as resp:
                        if resp.status == 200:
                            image = PILImage.open(io.BytesIO(await resp.read()))
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
        check, msg = await asyncio.to_thread(baidu_judge.judge, llm_result_str)
        if not check:
            return MessageResult(f"你的提问得到的回复【百度内容审核】未通过，不予回复。\n\n{msg}")
    # 发送信息
    try:
        return MessageResult(llm_result_str)
    except BaseException as e:
        logger.info("回复消息错误: \n"+str(e))
