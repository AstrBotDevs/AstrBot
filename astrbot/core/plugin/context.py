import heapq
from asyncio import Queue
from . import RegisteredPlugin, PluginMetadata
from typing import List, Dict, Awaitable, Union
from dataclasses import dataclass

from astrbot.core.platform import Platform
from astrbot.core.db import BaseDatabase
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.utils.func_call import FuncCall
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.message.message_event_result import MessageChain

@dataclass
class CommandMetadata():
    '''
    显式指令
    '''
    plugin_name: str
    plugin_metadata: PluginMetadata
    handler: Awaitable
    use_regex: bool = False
    ignore_prefix: bool = False
    description: str = ""
    
@dataclass
class EventListenerMetadata():
    '''
    事件监听器
    '''
    plugin_name: str
    plugin_metadata: PluginMetadata
    handler: Awaitable
    description: str = ""
    after_commands: bool = False


class Context:
    '''
    暴露给插件的接口上下文，用于注册指令、事件监听器、消息平台、模型提供商等。
    '''
    # 事件队列。消息平台通过事件队列传递消息事件。
    _event_queue: Queue = None
    
    # AstrBot 配置信息
    _config: AstrBotConfig = None
    
    # AstrBot 数据库
    _db: BaseDatabase = None
    
    # 维护了注册的插件的信息
    registered_plugins: List[RegisteredPlugin] = []
    
    # 维护了插件注册的指令的信息的名字列表，用于优先级排序
    registered_commands: List[str] = []
    # 维护了插件注册的指令的信息
    commands_handler: Dict[str, CommandMetadata] = {}
    
    # 维护了插件注册的中间件的名字列表，用于优先级排序
    registered_listeners: List[str] = []
    # 维护了插件注册的中间件的信息
    listeners_handler: Dict[str, EventListenerMetadata] = {}
    
    # 维护了注册的平台的信息
    registered_platforms: List[Platform] = []
    
    # 维护了 LLM Tools 信息
    llm_tools: FuncCall = FuncCall()
    
    # 维护插件存储的数据
    plugin_data: Dict[str, Dict[str, any]] = {}
    
    def __init__(self, event_queue: Queue, config: AstrBotConfig, db: BaseDatabase):
        self._event_queue = event_queue
        self._config = config
        self._db = db

    def get_registered_plugin(self, plugin_name: str) -> RegisteredPlugin:
        for plugin in self.registered_plugins:
            if plugin.metadata.plugin_name == plugin_name:
                return plugin
        return None
    
    def register_listener(self,
                            plugin_name: str, 
                            name: str,
                            handler: Awaitable,
                            description: str = None,
                            after_commands: bool = False):
        '''
        注册一个事件监听器。
        
        after_commands: 是否在指令处理后执行。
        '''
        if name in self.registered_listeners:
            raise ValueError(f"Middleware {name} already exists.")
        self.registered_listeners.append(name)
        self.listeners_handler[name] = EventListenerMetadata(
            plugin_name=plugin_name,
            plugin_metadata=None,
            handler=handler,
            description=description,
            after_commands=after_commands
        )

    def register_commands(self, 
                          plugin_name: str, 
                          command_name: str, 
                          description: str, 
                          priority: int, 
                          handler: Awaitable,
                          use_regex: bool = False,
                          ignore_prefix: bool = False):
        '''
        注册插件指令。
        
        @param plugin_name: 插件名，注意需要和你的 metadata 中的一致。
        @param command_name: 指令名，如 "help"。不需要带前缀。
        @param description: 指令描述。
        @param priority: 优先级越高，越先被处理。合理的优先级应该在 1-10 之间。
        @param handler: 指令处理函数。函数参数：message: AstrMessageEvent, context: Context
        @param use_regex: 是否使用正则表达式匹配指令名。
        @param ignore_prefix: 是否忽略前缀。默认为 False。设置为 True 后，将不会检查用户设置的前缀。
        
        .. Example::
        
        ignore_prefix = False 时，用户输入 "/help" 时，会被识别为 "help" 指令。如果 ignore_prefix = True，则用户输入 "help" 也会被识别为 "help" 指令。
        '''
        for command in self.registered_commands:
            if command_name in command[1]:
                raise ValueError(f"Command {command_name} already exists.")
        if not handler:
            raise ValueError(f"Handler of {command_name} is None.")

        heapq.heappush(self.registered_commands, (-priority, command_name))
        self.commands_handler[command_name] = CommandMetadata(
            plugin_name=plugin_name,
            plugin_metadata=None,
            handler=handler,
            use_regex=use_regex,
            ignore_prefix=ignore_prefix,
            description=description
        )
        heapq.heapify(self.registered_commands)
    
    def register_platform(self, platform: Platform):
        '''
        注册一个消息平台。
        '''
        self.registered_platforms.append(platform)
        
    def register_llm_tool(self, name: str, func_args: list, desc: str, func_obj: Awaitable) -> None:
        '''
        为函数调用（function-calling / tools-use）添加工具。
        
        @param name: 函数名
        @param func_args: 函数参数列表，格式为 [{"type": "string", "name": "arg_name", "description": "arg_description"}, ...]
        @param desc: 函数描述
        @param func_obj: 异步处理函数。
        
        异步处理函数会接收到额外的的关键词参数：event: AstrMessageEvent, context: Context。
        '''
        self.llm_tools.add_func(name, func_args, desc, func_obj)
        
    def unregister_llm_tool(self, name: str) -> None:
        '''
        删除一个函数调用工具。
        '''
        self.llm_tools.remove_func(name)
    
    def get_config(self) -> AstrBotConfig:
        '''
        获取 AstrBot 配置信息。
        '''
        return self._config
    
    def get_db(self) -> BaseDatabase:
        '''
        获取 AstrBot 数据库。
        '''
        return self._db
    
    def get_event_queue(self) -> Queue:
        '''
        获取事件队列。
        '''
        return self._event_queue
    
    async def send_message(self, session: Union[str, MessageSesion], message_chain: MessageChain) -> bool:
        '''
        根据 session(unified_msg_origin) 发送消息。
        
        @param session: 消息会话。通过 event.session 或者 event.unified_msg_origin 获取。
        @param message_chain: 消息链。
        
        @return: 是否找到匹配的平台。
        
        当 session 为字符串时，会尝试解析为 MessageSesion 对象，如果解析失败，会抛出 ValueError 异常。
        '''
        
        if isinstance(session, str):
            try:
                session = MessageSesion.from_str(session)
            except BaseException as e:
                raise ValueError("不合法的 session 字符串: " + str(e))

        for platform in self.registered_platforms:
            if platform.meta().name == session.platform_name:
                await platform.send_by_session(session, message_chain)
                return True
        return False
    
    def set_data(self, plugin_name: str, key: str, value: any):
        '''
        设置插件数据。
        '''
        self.plugin_data[plugin_name][key] = value