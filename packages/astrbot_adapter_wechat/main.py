from astrbot.api import Context, AstrMessageEvent, MessageEventResult
from .wechat_platform_adapter import WechatPlatformAdapter
from astrbot.api import logger

class Main:
    def __init__(self, context: Context) -> None:        
        self.context = context
        platforms_config = context.get_config().platform
        settings = context.get_config().platform_settings
        for platform in platforms_config:
            if platform.name == "wechat" and platform.enable:
                self.context.register_platform(WechatPlatformAdapter(platform, settings, context.get_event_queue()))
                logger.info(f"已注册 wechat({platform.id}) 消息适配器。")
                
                self.context.register_commands("astrbot_adapter_wechat", "wechatid", "查看微信ID", 1, self.get_wechat_id)
                
    async def get_wechat_id(self, event: AstrMessageEvent):
        event.set_result(MessageEventResult().message("这个会话的微信ID是" + event.message_obj.raw_message.from_.username))