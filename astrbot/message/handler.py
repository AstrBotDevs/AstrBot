import time
import re
import asyncio
import traceback
import astrbot.message.unfit_words as uw

from typing import Dict
from astrbot.persist.helper import dbConn
from model.provider.provider import Provider
from model.command.manager import CommandManager
from type.message_event import AstrMessageEvent, MessageResult
from type.types import Context
from type.command import CommandResult
from SparkleLogging.utils.core import LogManager
from logging import Logger
from nakuru.entities.components import Image
import util.agent.web_searcher as web_searcher

logger: Logger = LogManager.GetLogger(log_name='astrbot')


class RateLimitHelper():
    def __init__(self, context: Context) -> None:
        self.user_rate_limit: Dict[int, int] = {}
        self.rate_limit_time: int = 60
        self.rate_limit_count: int = 10
        self.user_frequency = {}
        
        if 'limit' in context.base_config:
            if 'count' in context.base_config['limit']:
                self.rate_limit_count = context.base_config['limit']['count']
            if 'time' in context.base_config['limit']:
                self.rate_limit_time = context.base_config['limit']['time']
    
    def check_frequency(self, session_id: str) -> bool:
        '''
        检查发言频率
        '''
        ts = int(time.time())
        if session_id in self.user_frequency:
            if ts-self.user_frequency[session_id]['time'] > self.rate_limit_time:
                self.user_frequency[session_id]['time'] = ts
                self.user_frequency[session_id]['count'] = 1
                return True
            else:
                if self.user_frequency[session_id]['count'] >= self.rate_limit_count:
                    return False
                else:
                    self.user_frequency[session_id]['count'] += 1
                    return True
        else:
            t = {'time': ts, 'count': 1}
            self.user_frequency[session_id] = t
            return True

class ContentSafetyHelper():
    def __init__(self, context: Context) -> None:
        self.baidu_judge = None
        if 'baidu_api' in context.base_config and \
            'enable' in context.base_config['baidu_aip'] and \
            context.base_config['baidu_aip']['enable']:
            try:
                from astrbot.message.baidu_aip_judge import BaiduJudge
                self.baidu_judge = BaiduJudge(context.base_config['baidu_aip'])
                logger.info("已启用百度 AI 内容审核。")
            except BaseException as e:
                logger.error("百度 AI 内容审核初始化失败。")
                logger.error(e)
                
    async def check_content(self, content: str) -> bool:
        '''
        检查文本内容是否合法
        '''
        for i in uw.unfit_words_q:
            matches = re.match(i, content.strip(), re.I | re.M)
            if matches:
                return False
        if self.baidu_judge != None:
            check, msg = await asyncio.to_thread(self.baidu_judge.judge, content)
            if not check:
                logger.info(f"百度 AI 内容审核发现以下违规：{msg}")
                return False
        return True
    
    def filter_content(self, content: str) -> str:
        '''
        过滤文本内容
        '''
        for i in uw.unfit_words_q:
            content = re.sub(i, "*", content, flags=re.I)
        return content
    
    def baidu_check(self, content: str) -> bool:
        '''
        使用百度 AI 内容审核检查文本内容是否合法
        '''
        if self.baidu_judge != None:
            check, msg = self.baidu_judge.judge(content)
            if not check:
                logger.info(f"百度 AI 内容审核发现以下违规：{msg}")
                return False
        return True

class MessageHandler():
    def __init__(self, context: Context,
                 command_manager: CommandManager,
                 persist_manager: dbConn,
                 provider: Provider) -> None:
        self.context = context
        self.command_manager = command_manager
        self.persist_manager = persist_manager
        self.rate_limit_helper = RateLimitHelper(context)
        self.content_safety_helper = ContentSafetyHelper(context)
        self.llm_wake_prefix = self.context.base_config['llm_wake_prefix']
        if self.llm_wake_prefix:
            self.llm_wake_prefix = self.llm_wake_prefix.strip()
        self.nicks = self.context.nick
        self.provider = provider
        self.reply_prefix = str(self.context.reply_prefix)
    
    def set_provider(self, provider: Provider):
        self.provider = provider

    async def handle(self, message: AstrMessageEvent, llm_provider: Provider = None) -> MessageResult:
        '''
        Handle the message event, including commands, plugins, etc.
        
        `llm_provider`: the provider to use for LLM. If None, use the default provider
        '''
        msg_plain = message.message_str.strip()
        provider = llm_provider if llm_provider else self.provider
        inner_provider = False if llm_provider else True
        
        self.persist_manager.record_message(message.platform.platform_name, message.session_id)
        
        # TODO: this should be configurable
        if not message.message_str:
            return MessageResult("Hi~")
        
        # check the rate limit
        if not self.rate_limit_helper.check_frequency(message.message_obj.sender.user_id):
            return MessageResult(f'你的发言超过频率限制(╯▔皿▔)╯。\n管理员设置 {self.rate_limit_helper.rate_limit_time} 秒内只能提问{self.rate_limit_helper.rate_limit_count} 次。')

        # remove the nick prefix
        for nick in self.nicks:
            if msg_plain.startswith(nick):
                msg_plain = msg_plain.removeprefix(nick)
                break
            
        # scan candidate commands
        cmd_res = await self.command_manager.scan_command(message, self.context)
        if cmd_res:
            assert(isinstance(cmd_res, CommandResult))
            return MessageResult(
                cmd_res.message_chain,
                is_command_call=True,
                use_t2i=cmd_res.is_use_t2i
            )
        
        # check if the message is a llm-wake-up command
        if self.llm_wake_prefix and not msg_plain.startswith(self.llm_wake_prefix):
            logger.debug(f"消息 `{msg_plain}` 没有以 LLM 唤醒前缀 `{self.llm_wake_prefix}` 开头，忽略。")
            return
        
        if not provider:
            logger.debug("没有任何 LLM 可用，忽略。")
            return
        
        # check the content safety
        if not await self.content_safety_helper.check_content(msg_plain):
            return MessageResult("信息包含违规内容，由于机器人管理者开启内容安全审核，你的此条消息已被停止继续处理。")
        
        image_url = None
        for comp in message.message_obj.message:
            if isinstance(comp, Image):
                image_url = comp.url if comp.url else comp.file
                break
        web_search = self.context.web_search
        if not web_search and msg_plain.startswith("ws"):
            # leverage web search feature
            web_search = True
            msg_plain = msg_plain.removeprefix("ws").strip()
        
        try:
            if web_search:
                llm_result = await web_searcher.web_search(msg_plain, provider, message.session_id, inner_provider)
            else:
                llm_result = await provider.text_chat(
                    prompt=msg_plain, 
                    session_id=message.session_id, 
                    image_url=image_url
                )
        except BaseException as e:
            logger.error(traceback.format_exc())
            logger.error(f"LLM 调用失败。")
            return MessageResult("AstrBot 请求 LLM 资源失败：" + str(e))
        
        # concatenate the reply prefix
        if self.reply_prefix:
            llm_result = self.reply_prefix + llm_result
        
        # mask the unsafe content
        llm_result = self.content_safety_helper.filter_content(llm_result)
        check = self.content_safety_helper.baidu_check(llm_result)
        if not check:
            return MessageResult("LLM 输出的信息包含违规内容，由于机器人管理者开启了内容安全审核，该条消息已拦截。")
        
        return MessageResult(llm_result)