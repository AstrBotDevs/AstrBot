import asyncio, re
import inspect
import traceback
from typing import List, Union
from .platform import AstrMessageEvent
from .config.astrbot_config import AstrBotConfig
from .message_event_result import MessageEventResult, CommandResult, MessageChain
from .plugin import PluginManager, Context, CommandMetadata
from .provider import Provider
from nakuru.entities.components import *
from core import logger
from core import html_renderer

class CommandTokens():
    def __init__(self) -> None:
        self.tokens = []
        self.len = 0
        
    def get(self, idx: int):
        if idx >= self.len:
            return None
        return self.tokens[idx].strip()

class CommandParser():
    def __init__(self):
        pass
        
    def parse(self, message: str):
        cmd_tokens = CommandTokens()
        cmd_tokens.tokens = message.split(" ")
        cmd_tokens.len = len(cmd_tokens.tokens)
        return cmd_tokens
    
    def regex_match(self, message: str, command: str) -> bool:
        return re.search(command, message, re.MULTILINE) is not None
    

class MessageEventHandler():
    '''
    处理消息事件。
    '''
    def __init__(self, config: AstrBotConfig, plugin_manager: PluginManager):
        self.config = config
        self.plugin_manager = plugin_manager
        self.command_parser = CommandParser()
    
    async def handle(self, event: AstrMessageEvent):
        '''
        处理消息事件。
        '''
        event.message_str = event.message_str.strip()
        for admin_id in self.config.admins_id:
            if event.get_sender_id() == admin_id:
                event.role = "admin"
                break
            
        # 检查 wake
        wake_prefixes = self.config.wake_prefix
        messages = event.get_messages()
        is_wake = False
        for wake_prefix in wake_prefixes:
            if event.message_str.startswith(wake_prefix):
                is_wake = True
                break
        if not is_wake:
            # 检查是否有 at 消息
            for message in messages:
                if isinstance(message, At) and (str(message.qq) == str(event.get_self_id()) or str(message.qq) == "all"):
                    is_wake = True
                    wake_prefix = ""
                    break
            # 检查是否是私聊
            if event.is_private_chat():
                is_wake = True
                wake_prefix = ""
        event.is_wake = is_wake
        
        # 处理事件监听器(在指令扫描之前)
        listeners = self.plugin_manager.context.registered_listeners
        listeners_handler = self.plugin_manager.context.listeners_handler
        for name in listeners:
            if listeners_handler[name].after_commands:
                continue
            ret = await listeners_handler[name].handler(event)
            if ret:
                event.set_result(ret)
            if event.get_result():
                return await self.post_handle(event)
        
        # 处理指令，指令带有指定过的前缀
        commands = self.plugin_manager.context.registered_commands
        commands_handler = self.plugin_manager.context.commands_handler
        
        # 扫描指令
        for command in commands:
            command = command[1]
            trig = False
            pre_ = ""
            if not commands_handler[command].ignore_prefix:
                pre_ = wake_prefix
            
            if commands_handler[command].use_regex:
                trig = self.command_parser.regex_match(event.message_str, pre_ + command)
            else:
                trig = event.message_str.startswith(pre_ + command)
            if trig:
                ret = await self.execute_handler(command, commands_handler[command], event)
                if ret:
                    event.set_result(ret)
                if event.get_result():
                    return await self.post_handle(event)
            
        # 处理事件监听器(在指令扫描之后)
        for name in listeners:
            if not listeners_handler[name].after_commands:
                continue
            ret = await listeners_handler[name].handler(event)
            if ret:
                event.set_result(ret)
            if event.get_result():
                return await self.post_handle(event)
                
    async def post_handle(self, event: AstrMessageEvent):
        result = event.get_result()
        if result.callback:
            await result.callback(event)
        
        # prefix
        if self.config.platform_settings.reply_prefix:
            result.chain.insert(0, Plain(self.config.platform_settings.reply_prefix))
            
        # t2i
        if (result.use_t2i_ is None and self.config.t2i) or result.use_t2i_:
            plain_str = ""
            for comp in result.chain:
                if isinstance(comp, Plain):
                    plain_str += "\n\n" + comp.text
                else:
                    break
            if plain_str and len(plain_str) > 150:
                url = await html_renderer.render_t2i(plain_str, return_url=True)
                if url:
                    result.chain = [Image.fromURL(url)]
                    
        logger.info(f"AstrBot -> {event.get_sender_name()}/{event.get_sender_id()}: {event._outline_chain(result.chain)}")
            
        await event.send(result)
    
    async def execute_handler(self,
                        command: str,
                        command_metadata: CommandMetadata,
                        message_event: AstrMessageEvent):
        logger.info(f"触发 {command}/({command_metadata.plugin_metadata.plugin_name} By {command_metadata.plugin_metadata.author}) 指令。")
        handler = command_metadata.handler
        try:
            if inspect.iscoroutinefunction(handler):
                command_result = await handler(message_event)
            else:
                command_result = handler(message_event)

            if command_result is not None:
                message_event.set_result(command_result)
        except TypeError as e:
            # 兼容旧版本插件
            if inspect.iscoroutinefunction(handler):
                command_result = await handler(message_event, self.plugin_manager.context)
            else:
                command_result = handler(message_event, self.plugin_manager.context)

            if command_result is not None:
                message_event.set_result(command_result)
        except BaseException as e:
            logger.error(traceback.format_exc())
            text = f"执行 {command}/({command_metadata.plugin_metadata.plugin_name} By {command_metadata.plugin_metadata.author}) 指令时发生了异常。{e}"
            message_event.set_result(MessageEventResult().message(text))