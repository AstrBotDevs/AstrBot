import asyncio
from asyncio import Task
from type.register import *
from typing import List, Awaitable
from logging import Logger
from util.cmd_config import CmdConfig
from util.t2i.renderer import TextToImageRenderer
from util.updator.astrbot_updator import AstrBotUpdator
from util.image_uploader import ImageUploader
from util.updator.plugin_updator import PluginUpdator
from model.plugin.command import PluginCommandBridge
from model.provider.provider import Provider


class Context:
    '''
    存放一些公用的数据，用于在不同模块(如core与command)之间传递
    '''

    def __init__(self):
        self.logger: Logger = None
        self.base_config: dict = None  # 配置（期望启动机器人后是不变的）
        self.config_helper: CmdConfig = None
        self.cached_plugins: List[RegisteredPlugin] = []  # 缓存的插件
        self.platforms: List[RegisteredPlatform] = []
        self.llms: List[RegisteredLLM] = []
        self.default_personality: dict = None
        
        self.unique_session = False # 独立会话
        self.version: str = None  # 机器人版本
        self.nick = None  # gocq 的唤醒词
        self.stat = {}
        self.t2i_mode = False
        self.web_search = False  # 是否开启了网页搜索
        self.reply_prefix = ""
        self.updator: AstrBotUpdator = None
        self.plugin_updator: PluginUpdator = None
        self.metrics_uploader = None
        
        self.plugin_command_bridge = PluginCommandBridge(self.cached_plugins)
        self.image_renderer = TextToImageRenderer()
        self.image_uploader = ImageUploader()
        self.message_handler = None # see astrbot/message/handler.py
        self.ext_tasks: List[Task] = []

    def register_commands(self, 
                          plugin_name: str, 
                          command_name: str, 
                          description: str, 
                          priority: int, 
                          handler: callable):
        '''
        注册插件指令。
        
        `plugin_name`: 插件名，注意需要和你的 metadata 中的一致。
        `command_name`: 指令名，如 "help"。不需要带前缀。
        `description`: 指令描述。
        `priority`: 优先级越高，越先被处理。合理的优先级应该在 1-10 之间。
        `handler`: 指令处理函数。函数参数：message: AstrMessageEvent, context: Context
        '''
        self.plugin_command_bridge.register_command(plugin_name, command_name, description, priority, handler)
        
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
        
        `provider`: Provider 对象。即你的实现需要继承 Provider 类。至少应该实现 text_chat() 方法。
        '''
        self.llms.append(RegisteredLLM(llm_name, provider, origin))
    
    def find_platform(self, platform_name: str) -> RegisteredPlatform:
        for platform in self.platforms:
            if platform_name == platform.platform_name:
                return platform
            
        raise ValueError("couldn't find the platform you specified")
