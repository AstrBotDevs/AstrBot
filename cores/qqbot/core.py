import io

import botpy
from PIL import Image
from botpy.message import Message
from botpy.types.message import Reference
import yaml
import re
from util.errors.errors import PromptExceededError
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

# 人格信息
now_personality = {}

# 机器人私聊模式
direct_message_mode = True

# 适配pyinstaller
abs_path = os.path.dirname(os.path.realpath(sys.argv[0])) + '/'

# 版本
version = '2.9'

# 语言模型提供商
REV_CHATGPT = 'rev_chatgpt'
OPENAI_OFFICIAL = 'openai_official'
REV_ERNIE = 'rev_ernie'
REV_EDGEGPT = 'rev_edgegpt'
provider = ''

# 逆向库对象及负载均衡
rev_chatgpt = []

# gpt配置信息
gpt_config = {}

# 百度内容审核实例
baidu_judge = None

# 回复前缀
reply_prefix = ''


def new_sub_thread(func, args=()):
    thread = threading.Thread(target=func, args=args, daemon=True)
    thread.start() 

class botClient(botpy.Client):
    # 收到At消息
    async def on_at_message_create(self, message: Message):
        toggle_count(at=True, message=message)
        message_reference = Reference(message_id=message.id, ignore_get_message_error=False)
        # executor.submit(oper_msg, message, True)
        new_sub_thread(oper_msg, (message, True, message_reference))
        # await oper_msg(message=message, at=True)

    # 收到私聊消息
    async def on_direct_message_create(self, message: DirectMessage):
        if direct_message_mode:
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
    global chatgpt, provider, rev_chatgpt, baidu_judge, rev_ernie, rev_edgegpt
    global reply_prefix, now_personality, gpt_config, config, uniqueSession, frequency_count, frequency_time,announcement, direct_message_mode, version
    global command_openai_official, command_rev_chatgpt, command_rev_edgegpt

    provider = prov
    config = cfg
    reply_prefix_config = None
    if 'reply_prefix' in cfg:
        reply_prefix_config = cfg['reply_prefix']

    # 语言模型提供商
    if prov == REV_CHATGPT:
        if 'account' in cfg['rev_ChatGPT']:
            from model.provider.provider_rev_chatgpt import ProviderRevChatGPT
            from model.command.command_rev_chatgpt import CommandRevChatGPT
            for i in range(0, len(cfg['rev_ChatGPT']['account'])):
                try:
                    print(f"[System] 创建rev_ChatGPT负载{str(i)}: " + str(cfg['rev_ChatGPT']['account'][i]))
                    revstat = {
                        'obj': ProviderRevChatGPT(cfg['rev_ChatGPT']['account'][i]),
                        'busy': False
                    }
                    rev_chatgpt.append(revstat)
                except:
                    print("[System] 创建rev_ChatGPT负载失败")
            command_rev_chatgpt = CommandRevChatGPT(rev_chatgpt)

            if REV_CHATGPT in reply_prefix_config:
                reply_prefix = reply_prefix_config[REV_CHATGPT]
        else:
            input("[System-err] 请退出本程序, 然后在配置文件中填写rev_ChatGPT相关配置")
    elif prov == OPENAI_OFFICIAL:
        from model.provider.provider_openai_official import ProviderOpenAIOfficial
        from model.command.command_openai_official import CommandOpenAIOfficial
        chatgpt = ProviderOpenAIOfficial(cfg['openai'])
        command_openai_official = CommandOpenAIOfficial(chatgpt)
        if OPENAI_OFFICIAL in reply_prefix_config:
            reply_prefix = reply_prefix_config[OPENAI_OFFICIAL]
    # elif prov == REV_ERNIE:
    #     from addons.revERNIE import revernie
    #     rev_ernie = revernie.wx
    elif prov == REV_EDGEGPT:
        from model.provider.provider_rev_edgegpt import ProviderRevEdgeGPT
        from model.command.command_rev_edgegpt import CommandRevEdgeGPT
        rev_edgegpt = ProviderRevEdgeGPT()
        command_rev_edgegpt = CommandRevEdgeGPT(rev_edgegpt)
        if REV_EDGEGPT in reply_prefix_config:
            reply_prefix = reply_prefix_config[REV_EDGEGPT]

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

    # 得到版本
    if 'version' in cfg:
        try:
            f = open(abs_path+"version.txt", 'r', encoding='utf-8')
            version = f.read()
        except:
            print('[System-Err] 读取更新记录文件失败')
        # version = 'Unknown'
        # print("[System] QQChannelChatGPT版本: "+str(version))

    # 得到发言频率配置
    if 'limit' in cfg:
        print('[System] 发言频率配置: '+str(cfg['limit']))
        if 'count' in cfg['limit']:
            frequency_count = cfg['limit']['count']
        if 'time' in cfg['limit']:
            frequency_time = cfg['limit']['time']
    
    announcement += '[QQChannelChatGPT项目，觉得好用的话欢迎前往Github给Star]\n所有回答与腾讯公司无关。出现问题请前往[GPT机器人]官方频道\n\n'
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

    print("\n[System] 如果有任何问题，请在https://github.com/Soulter/QQChannelChatGPT上提交issue说明问题！或者添加QQ：905617992")
    print("[System] 请给https://github.com/Soulter/QQChannelChatGPT点个star!")
    print("[System] 请给https://github.com/Soulter/QQChannelChatGPT点个star!")
    # input("\n仔细阅读完以上信息后，输入任意信息并回车以继续")
    try:
        run_bot(cfg['qqbot']['appid'], cfg['qqbot']['token'])
    except BaseException as e:
        input(f"\n[System-Error] 启动QQ机器人时出现错误，原因如下：{e}\n可能是没有填写QQBOT appid和token？请在config中完善你的appid和token\n配置教程：https://soulter.top/posts/qpdg.html\n")

        
'''
启动机器人
'''
def run_bot(appid, token):
    intents = botpy.Intents(public_guild_messages=True, direct_message=True) 
    global client
    client = botClient(intents=intents)
    client.run(appid=appid, token=token)

'''
负载均衡，得到逆向ChatGPT回复
'''
def get_rev_ChatGPT_response(prompts_str):
    res = ''
    print("[Debug] "+str(rev_chatgpt))
    for revstat in rev_chatgpt:
        if not revstat['busy']:
            try:
                revstat['busy'] = True
                print("[Debug] 使用逆向ChatGPT回复ing", end='', flush=True)
                res = revstat['obj'].chat(prompts_str)
                print("OK")
                revstat['busy'] = False
                # 处理结果文本
                chatgpt_res = res.strip()
                return res
            except Exception as e:
                print("[System-Error] 逆向ChatGPT回复失败" + str(e))
                try:
                    if e.code == 2:
                        print("[System-Error] 频率限制，正在切换账号。"+ str(e))
                        continue
                    else:
                        res = '所有的非忙碌OpenAI账号经过测试都暂时出现问题，请稍后再试或者联系管理员~'
                        return res
                except BaseException:
                    continue
    res = '所有的OpenAI账号都有负载, 请稍后再试~'
    return res


'''
回复QQ消息
'''
def send_qq_msg(message, res, image_mode=False, msg_ref = None):
    if not image_mode:
        try:
            if msg_ref is not None:
                reply_res = asyncio.run_coroutine_threadsafe(message.reply(content=res, message_reference = msg_ref), client.loop)
            else:
                reply_res = asyncio.run_coroutine_threadsafe(message.reply(content=res), client.loop)
            reply_res.result()
        except BaseException as e:
            if "msg over length" in str(e):
                split_res = []
                split_res.append(res[:len(res)//2])      
                split_res.append(res[len(res)//2:])
                for i in split_res:
                    if msg_ref is not None:
                        reply_res = asyncio.run_coroutine_threadsafe(message.reply(content=i, message_reference = msg_ref), client.loop)
                    else:
                        reply_res = asyncio.run_coroutine_threadsafe(message.reply(content=i), client.loop)
                    reply_res.result()
            else:
                print("[System-Error] 回复QQ消息失败")
                raise e
    else:
        pic_res = requests.get(str(res), stream=True)
        if pic_res.status_code == 200:
            # 将二进制数据转换成图片对象
            image = Image.open(io.BytesIO(pic_res.content))
            # 保存图片到本地
            image.save('tmp_image.jpg')
        asyncio.run_coroutine_threadsafe(message.reply(file_image='tmp_image.jpg', content=""), client.loop)


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
处理消息
'''
def oper_msg(message, at=False, msg_ref = None):
    global session_dict, provider
    print("[QQBOT] 接收到消息："+ str(message.content))
    qq_msg = ''
    session_id = ''
    name = ''
    user_id = message.author.id
    user_name = message.author.username
    
    # 检查发言频率
    if not check_frequency(user_id):
        send_qq_msg(message, f'{user_name}的发言超过频率限制(╯▔皿▔)╯。\n{frequency_time}秒内只能提问{frequency_count}次。')
        return

    logf.write("[QQBOT] "+ str(message.content)+'\n')
    logf.flush()

    if at:
        qq_msg = message.content
        lines = qq_msg.splitlines()
        for i in range(len(lines)):
            lines[i] = re.sub(r"<@!\d+>", "", lines[i])
        qq_msg = "\n".join(lines).lstrip().strip()

        if uniqueSession:
            session_id = user_id
        else:
            session_id = message.channel_id
    else:
        qq_msg = message.content
        session_id = user_id
        
    if uniqueSession:
        name = user_name
    else:
        name = "频道"

    # command_type = -1
    # # 特殊指令
    # if qq_msg == "/继续":
    #     qq_msg = "继续"
    # # 普通指令
    # else:
    #     # 如果第一个字符是/，则为指令
    #     if qq_msg[0] == "/":
    #         res, go, command_type = command_oper(qq_msg, message, session_id, name, user_id, user_name, at)
    #         send_qq_msg(message, res)
    #         if not go:
    #             return
    # if command_type == 1 and 'prompt' in now_personality:
    #     # 设置人格
    #     qq_msg = now_personality['prompt']

    # 这里是预设，你可以按需更改
    if qq_msg.strip() == 'hello' or qq_msg.strip() == '你好' or qq_msg.strip() == '':
        send_qq_msg(message, f"你好呀🥰，输入/help查看指令噢", msg_ref=msg_ref)
        return

    # if qq_msg.strip() == '傻逼' or qq_msg.strip() == 'sb':
    #     send_qq_msg(message, f"好好好")
    #     return

    # if '喜多' in qq_msg:
    #     send_qq_msg(message, 'http://rn2ztkeap.hn-bkt.clouddn.com/xd1.gif', True)
    # if '台湾' in qq_msg or 'taiwan' in qq_msg:
    #     send_qq_msg(message, "声明：台湾是中国的一部分。\n下面否定此结论的回答全部无效。")
    
    # 关键词拦截器
    for i in uw.unfit_words_q:
        matches = re.match(i, qq_msg.strip(), re.I | re.M)
        if matches:
            send_qq_msg(message, f"你的提问得到的回复未通过【自有关键词拦截】服务，不予回复。", msg_ref=msg_ref)
            return
    if baidu_judge != None:
        check, msg = baidu_judge.judge(qq_msg)
        if not check:
            send_qq_msg(message, f"你的提问得到的回复未通过【百度AI内容审核】服务，不予回复。\n\n{msg}", msg_ref=msg_ref)
            return
        
    chatgpt_res = ""

    if provider == OPENAI_OFFICIAL:
        hit, command_result = command_openai_official.check_command(qq_msg, session_id, user_name)
        print(f"{hit} {command_result}")
        if hit:
            if command_result != None and command_result[0]:
                send_qq_msg(message, command_result[1], msg_ref=msg_ref)
            else:
                send_qq_msg(message, f"指令调用错误: \n{command_result[1]}", msg_ref=msg_ref)
            return
        # 请求chatGPT获得结果
        try:
            chatgpt_res = reply_prefix + chatgpt.text_chat(qq_msg, session_id)
        except (BaseException) as e:
            print("[System-Err] OpenAI API错误。原因如下:\n"+str(e))
            if 'exceeded' in str(e):
                send_qq_msg(message, f"OpenAI API错误。原因：\n{str(e)} \n超额了。可自己搭建一个机器人(Github仓库：QQChannelChatGPT)")
                return
            else:
                f_res = re.sub(r'(https|http)?:\/\/(\w|\.|\/|\?|\=|\&|\%)*\b', '[被隐藏的链接]', str(e), flags=re.MULTILINE)
                f_res = f_res.replace(".", "·")
                send_qq_msg(message, f"OpenAI API错误。原因如下：\n{f_res} \n前往官方频道反馈~")
                return
        
    elif provider == REV_CHATGPT:
        hit, success, res = command_rev_chatgpt.check_command(qq_msg)
        if hit:
            if success:
                send_qq_msg(message, res, msg_ref=msg_ref)
            else:
                send_qq_msg(message, f"指令调用错误: \n{res}", msg_ref=msg_ref)
            return
        try:
            chatgpt_res = reply_prefix+str(get_rev_ChatGPT_response(qq_msg))
        except BaseException as e:
            print("[System-Err] Rev ChatGPT API错误。原因如下:\n"+str(e))
            send_qq_msg(message, f"Rev ChatGPT API错误。原因如下：\n{str(e)} \n前往官方频道反馈~")
            return
    # elif provider == REV_ERNIE:
    #     try:
    #         chatgpt_res = reply_prefix+str(rev_ernie.chatViaSelenium(qq_msg))
    #     except BaseException as e:
    #         print("[System-Err] Rev ERNIE API错误。原因如下:\n"+str(e))
    #         send_qq_msg(message, f"Rev ERNIE API错误。原因如下：\n{str(e)} \n前往官方频道反馈~")
    #         return
    elif provider == REV_EDGEGPT:
        hit, success, res = command_rev_chatgpt.check_command(qq_msg)
        if hit:
            if success:
                send_qq_msg(message, res, msg_ref=msg_ref)
            else:
                send_qq_msg(message, f"指令调用错误: \n{res}", msg_ref=msg_ref)
            return
        try:
            if rev_edgegpt.is_busy():
                send_qq_msg(message, f"[RevBing] 正忙，请稍后再试",msg_ref=msg_ref)
                return
            else:
                chatgpt_res = reply_prefix
                chatgpt_res += str(asyncio.run_coroutine_threadsafe(rev_edgegpt.chat(qq_msg), client.loop).result())
        except BaseException as e:
            print("[System-Err] Rev NewBing API错误。原因如下:\n"+str(e))
            send_qq_msg(message, f"Rev NewBing API错误。原因如下：\n{str(e)} \n前往官方频道反馈~")
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
            send_qq_msg(message, f"你的提问得到的回复【百度内容审核】未通过，不予回复。\n\n{msg}", msg_ref=msg_ref)
            return
    # 发送qq信息
    try:
        # 防止被qq频道过滤消息
        gap_chatgpt_res = judged_res.replace(".", " . ")
        send_qq_msg(message, ''+gap_chatgpt_res, msg_ref=msg_ref)
        # 发送信息
    except BaseException as e:
        print("QQ频道API错误: \n"+str(e))
        f_res = ""
        for t in chatgpt_res:
            f_res += t + ' '
        try:
            send_qq_msg(message, ''+f_res, msg_ref=msg_ref)
            # send(message, f"QQ频道API错误：{str(e)}\n下面是格式化后的回答：\n{f_res}")
        except BaseException as e:
            # 如果还是不行则过滤url
            f_res = re.sub(r'(https|http)?:\/\/(\w|\.|\/|\?|\=|\&|\%)*\b', '[被隐藏的链接]', str(e), flags=re.MULTILINE)
            f_res = f_res.replace(".", "·")
            send_qq_msg(message, ''+f_res, msg_ref=msg_ref)
            # send(message, f"QQ频道API错误：{str(e)}\n下面是格式化后的回答：\n{f_res}")

        
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