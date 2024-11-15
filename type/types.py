import asyncio, os, time
from asyncio import Task
from type.register import *
from typing import List, Awaitable
from logging import Logger
from util.cmd_config import AstrBotConfig
from util.t2i.renderer import TextToImageRenderer
from util.updator.astrbot_updator import AstrBotUpdator
from util.image_uploader import ImageUploader
from util.updator.plugin_updator import PluginUpdator
from type.command import CommandResult
from type.middleware import Middleware
from type.astrbot_message import MessageType
from model.plugin.command import PluginCommandBridge
from model.provider.provider import Provider
from util.log import LogBroker
from util.metrics import MetricUploader


class Context:
    '''
    存放一些公用的数据，用于在不同模块(如core与command)之间传递
    '''

    def __init__(self):
        self.running = True
        self.logger: Logger = None
        self.config_helper: AstrBotConfig = None
        self.cached_plugins: List[RegisteredPlugin] = []  # 缓存的插件
        self.platforms: List[RegisteredPlatform] = []
        self.llms: List[RegisteredLLM] = []
        self.default_personality: dict = None
        
        self.metrics_uploader: MetricUploader = None
        self.updator: AstrBotUpdator = None
        self.plugin_updator: PluginUpdator = None
        self.plugin_command_bridge = PluginCommandBridge(self.cached_plugins)
        self.image_renderer = TextToImageRenderer()
        self.image_uploader = ImageUploader()
        self.message_handler = None # see astrbot/message/handler.py
        self.ext_tasks: List[Task] = []
        self.middlewares: List[Middleware] = []
        
        self.command_manager = None
        self.running = True
        self._loop = asyncio.get_event_loop()
        self._start_running = int(time.time())
        
        self.log_broker = LogBroker()

    def register_commands(self, 
                          plugin_name: str, 
                          command_name: str, 
                          description: str, 
                          priority: int, 
                          handler: callable,
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
        self.plugin_command_bridge.register_command(plugin_name, 
                                                    command_name, 
                                                    description, 
                                                    priority, 
                                                    handler, 
                                                    use_regex,
                                                    ignore_prefix)
        
    def register_task(self, coro: Awaitable, task_name: str):
        '''
        注册任务。适用于需要长时间运行的插件。
        
        `coro`: 协程对象
        `task_name`: 任务名，用于标识任务。自定义即可。
        '''
        task = asyncio.create_task(coro, name=task_name)
        self.ext_tasks.append(task)
        
    def register_provider(self, llm_name: str, provider: Provider, origin: str = ''):
        '''
        注册一个提供 LLM 资源的 Provider。
        
        `llm_name`: 自定义的用于识别 Provider 的名称。在 AstrBot 配置中，是 `llm` 字段下的 `id` 字段。
        `provider`: Provider 对象。即你的实现需要继承 Provider 类。至少应该实现 text_chat() 方法。
        '''
        self.llms.append(RegisteredLLM(llm_name, provider, origin))
        
    def register_llm_tool(self, tool_name: str, params: list, desc: str, func: callable):
        '''
        为函数调用（function-calling / tools-use）添加工具。
        
        @param name: 函数名
        @param func_args: 函数参数列表，格式为 [{"type": "string", "name": "arg_name", "description": "arg_description"}, ...]
        @param desc: 函数描述
        @param func_obj: 处理函数
        '''
        self.message_handler.llm_tools.add_func(tool_name, params, desc, func)
    
    def unregister_llm_tool(self, tool_name: str):
        '''
        删除一个函数调用工具。
        '''
        self.message_handler.llm_tools.remove_func(tool_name)
        
    def register_middleware(self, middleware: Middleware):
        '''
        注册一个中间件。所有的消息事件都会经过中间件处理，然后再进入 LLM 聊天模块。
        
        在 AstrBot 中，会对到来的消息事件首先检查指令，然后再检查中间件。触发指令后将不会进入 LLM 聊天模块，而中间件会。
        '''
        self.middlewares.append(middleware)
     
    def find_platform(self, platform_name: str) -> RegisteredPlatform:
        for platform in self.platforms:
            if platform_name == platform.platform_name:
                return platform
        
        if not os.environ.get('TEST_MODE', 'off') == 'on': # 测试模式下不报错
            raise ValueError("couldn't find the platform you specified")

    async def send_message(self, unified_msg_origin: str, message: CommandResult):
        '''
        发送消息。
        
        `unified_msg_origin`: 统一消息来源
        `message`: 消息内容
        '''
        l = unified_msg_origin.split(":")
        if len(l) != 3:
            raise ValueError("Invalid unified_msg_origin")
        platform_name, message_type, id = l
        platform = self.find_platform(platform_name)
        await platform.platform_instance.send_msg_new(MessageType(message_type), id, message)
    
    def get_current_llm_provider(self) -> Provider:
        '''
        获取当前的 LLM Provider。
        '''
        return self.message_handler.provider