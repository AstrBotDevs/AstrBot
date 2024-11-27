from astrbot.api import Context
from .aiocqhttp_platform_adapter import AiocqhttpAdapter
from astrbot.api import logger

class Main:
    def __init__(self, context: Context) -> None:
        self.context = context
        platforms_config = context.get_config().platform
        settings = context.get_config().platform_settings
        for platform in platforms_config:
            if platform.name == "aiocqhttp" and platform.enable:
                self.context.register_platform(AiocqhttpAdapter(platform, settings, context.get_event_queue()))
                logger.info(f"已注册 aiocqhttp({platform.id}) 消息适配器。")