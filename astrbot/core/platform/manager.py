from astrbot.core.config.astrbot_config import AstrBotConfig
from .platform import Platform
from typing import List
from asyncio import Queue
from .register import platform_cls_map
from astrbot.core import logger
from .sources.webchat.webchat_adapter import WebChatAdapter

class PlatformManager():
    def __init__(self, config: AstrBotConfig, event_queue: Queue):
        self.platform_insts: List[Platform] = []
        '''加载的 Platform 的实例'''
        
        self.platforms_config = config['platform']
        self.settings = config['platform_settings']
        self.event_queue = event_queue
        
        for platform in self.platforms_config:
            if not platform['enable']:
                continue
            match platform['type']:
                case "aiocqhttp":
                    from .sources.aiocqhttp.aiocqhttp_platform_adapter import AiocqhttpAdapter  # noqa: F401
                case "qq_official":
                    from .sources.qqofficial.qqofficial_platform_adapter import QQOfficialPlatformAdapter # noqa: F401
                case "vchat":
                    from .sources.vchat.vchat_platform_adapter import VChatPlatformAdapter # noqa: F401
        

    async def initialize(self):
        for platform in self.platforms_config:
            if not platform['enable']:
                continue
            if platform['type'] not in platform_cls_map:
                logger.error(f"未找到适用于 {platform['type']}({platform['id']}) 平台适配器，请检查是否已经安装或者名称填写错误。已跳过。")
                continue
            cls_type = platform_cls_map[platform['type']]
            logger.info(f"尝试实例化 {platform['type']}({platform['id']}) 平台适配器 ...")
            inst = cls_type(platform, self.settings, self.event_queue)
            self.platform_insts.append(inst)
        
        self.platform_insts.append(WebChatAdapter({}, self.settings, self.event_queue))
                    
    def get_insts(self):
        return self.platform_insts