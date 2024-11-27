import botpy, logging
# delete qqbotpy's logger
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

from astrbot.api import Context
from .qqofficial_platform_adapter import QQOfficialPlatformAdapter
from astrbot.api import logger

class Main:
    def __init__(self, context: Context) -> None:        
        self.context = context
        platforms_config = context.get_config().platform
        settings = context.get_config().platform_settings
        for platform in platforms_config:
            if platform.name == "qq_official" and platform.enable:
                self.context.register_platform(QQOfficialPlatformAdapter(platform, settings, context.get_event_queue()))
                logger.info(f"已注册 qq_official({platform.id}) 消息适配器。")