import time, json
import re, os
import asyncio
import traceback
import astrbot.message.unfit_words as uw

from typing import Dict
from astrbot.db import BaseDatabase
from model.provider.provider import Provider
from model.command.manager import CommandManager
from type.message_event import AstrMessageEvent, MessageResult
from type.types import Context
from type.command import CommandResult
from util.log import LogManager
from logging import Logger
from nakuru.entities.components import Image
from util.agent.func_call import FuncCall
from openai._exceptions import *
from openai.types.chat.chat_completion_message_tool_call import Function

logger: Logger = LogManager.GetLogger(log_name='astrbot')


class RateLimitHelper():
    def __init__(self, context: Context) -> None:
        self.user_rate_limit: Dict[int, int] = {}
        rl = context.config_helper.platform_settings.rate_limit
        self.rate_limit_time: int = rl.time
        self.rate_limit_count: int = rl.count
        self.user_frequency = {}

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
        aip = context.config_helper.content_safety.baidu_aip
        if aip.enable:
            try:
                from astrbot.message.baidu_aip_judge import BaiduJudge
                self.baidu_judge = BaiduJudge(aip)
                logger.info("已启用百度 AI 内容审核。")
            except ImportError as e:
                logger.error("检测到库依赖不完整，将不会启用百度 AI 内容审核。请先使用 pip 安装 `baidu_aip` 包。")
                logger.error(e)
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
                 db_helper: BaseDatabase) -> None:
        self.context = context
        self.command_manager = command_manager
        self.db_helper = db_helper
        self.rate_limit_helper = RateLimitHelper(context)
        self.content_safety_helper = ContentSafetyHelper(context)
        self.llm_wake_prefix = self.context.config_helper.llm_settings.wake_prefix
        if self.llm_wake_prefix:
            self.llm_wake_prefix = self.llm_wake_prefix.strip()
        self.provider = self.context.llms[0].llm_instance if len(self.context.llms) > 0 else None
        self.reply_prefix = str(self.context.config_helper.platform_settings.reply_prefix)        
        self.llm_tools = FuncCall(self.provider)

    def set_provider(self, provider: Provider):
        self.provider = provider

    async def handle(self, message: AstrMessageEvent, llm_provider: Provider = None) -> MessageResult:
        '''
        Handle the message event, including commands, plugins, etc.
        
        `llm_provider`: the provider to use for LLM. If None, use the default provider
        '''
        msg_plain = message.message_str.strip()
        provider = llm_provider if llm_provider else self.provider        
        
        # TODO: this should be configurable
        # if not message.message_str:
        #     return MessageResult("Hi~")
        
        # check the rate limit
        if not self.rate_limit_helper.check_frequency(message.message_obj.sender.user_id):
            logger.warning(f"用户 {message.message_obj.sender.user_id} 的发言频率超过限制，已忽略。")
            return

        # remove the nick prefix
        for nick in self.context.config_helper.wake_prefix:
            if msg_plain.startswith(nick):
                msg_plain = msg_plain.removeprefix(nick)
                break
        message.message_str = msg_plain

        # scan candidate commands
        cmd_res = await self.command_manager.scan_command(message, self.context)
        if cmd_res:
            assert(isinstance(cmd_res, CommandResult))
            return MessageResult(
                cmd_res.message_chain,
                is_command_call=True,
                use_t2i=cmd_res.is_use_t2i
            )
            
        # middlewares
        for middleware in self.context.middlewares:
            try:
                logger.info(f"执行中间件 {middleware.origin}/{middleware.name}...")
                await middleware.func(message, self.context)
            except BaseException as e:
                logger.error(f"中间件 {middleware.origin}/{middleware.name} 处理消息时发生异常：{e}，跳过。")
                logger.error(traceback.format_exc())
        
        if message.only_command:
            return
        
        # next is the LLM part
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
        try:
            if not self.llm_tools.empty():
                # tools-use
                tool_use_flag = True
                llm_result = await provider.text_chat(
                    prompt=msg_plain, 
                    session_id=message.session_id, 
                    tools=self.llm_tools.get_func()
                )
                
                if isinstance(llm_result, Function):
                    logger.debug(f"function-calling: {llm_result}")
                    func_obj = None
                    for i in self.llm_tools.func_list:
                        if i["name"] == llm_result.name:
                            func_obj = i["func_obj"]
                            break
                    if not func_obj:
                        return MessageResult("AstrBot Function-calling 异常：未找到请求的函数调用。")
                    try:
                        args = json.loads(llm_result.arguments)
                        args['ame'] = message
                        args['context'] = self.context
                        try:
                            cmd_res = await func_obj(**args)
                        except TypeError as e:
                            args.pop('ame')
                            args.pop('context')
                            cmd_res = await func_obj(**args)
                        if isinstance(cmd_res, CommandResult):
                            return MessageResult(
                                cmd_res.message_chain,
                                is_command_call=True,
                                use_t2i=cmd_res.is_use_t2i
                            )
                        elif isinstance(cmd_res, str):
                            return MessageResult(cmd_res)
                        elif not cmd_res:
                            return
                        else:
                            return MessageResult(f"AstrBot Function-calling 异常：调用：{llm_result} 时，返回了未知的返回值类型。")
                    except BaseException as e:
                        traceback.print_exc()
                        return MessageResult("AstrBot Function-calling 异常：" + str(e))
                else:
                    return MessageResult(llm_result)
        
            else:
                # normal chat
                tool_use_flag = False
                llm_result = await provider.text_chat(
                    prompt=msg_plain, 
                    session_id=message.session_id, 
                    image_url=image_url
                )
        except BadRequestError as e:
            if tool_use_flag:
                # seems like the model don't support function-calling
                logger.error(f"error: {e}. Using local function-calling implementation")
                
                try:
                    # use local function-calling implementation
                    args = {
                        'question': llm_result,
                        'func_definition': self.llm_tools.func_dump(),
                    }
                    _, has_func = await self.llm_tools.func_call(**args)
                    
                    if not has_func:
                        # normal chat
                        llm_result = await provider.text_chat(
                            prompt=msg_plain, 
                            session_id=message.session_id, 
                            image_url=image_url
                        )
                except BaseException as e:
                    logger.error(traceback.format_exc())
                    return CommandResult("AstrBot Function-calling 异常：" + str(e))

        except BaseException as e:
            logger.error(traceback.format_exc())
            logger.error(f"LLM 调用失败。")
            return MessageResult("AstrBot 请求 LLM 资源失败：" + str(e))

        # concatenate reply prefix
        if self.reply_prefix:
            llm_result = self.reply_prefix + llm_result
        
        # mask unsafe content
        llm_result = self.content_safety_helper.filter_content(llm_result)
        check = self.content_safety_helper.baidu_check(llm_result)
        if not check:
            return MessageResult("LLM 输出的信息包含违规内容，由于机器人管理者开启了内容安全审核，该条消息已拦截。")
        
        return MessageResult(llm_result)