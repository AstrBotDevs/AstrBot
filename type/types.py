from type.register import *
from typing import List
from logging import Logger
from util.cmd_config import CmdConfig
from util.t2i.renderer import TextToImageRenderer
from util.updator.astrbot_updator import AstrBotUpdator
from util.image_uploader import ImageUploader
from util.updator.plugin_updator import PluginUpdator
from model.plugin.command import PluginCommandBridge


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
        
        self.plugin_command_bridge = PluginCommandBridge(self.cached_plugins)
        self.image_renderer = TextToImageRenderer()
        self.image_uploader = ImageUploader()

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
        `handler`: 指令处理函数。
        '''
        self.plugin_command_bridge.register_command(plugin_name, command_name, description, priority, handler)
        
    
    def find_platform(self, platform_name: str) -> RegisteredPlatform:
        for platform in self.platforms:
            if platform_name == platform.platform_name:
                return platform
            
        raise ValueError("couldn't find the platform you specified")
