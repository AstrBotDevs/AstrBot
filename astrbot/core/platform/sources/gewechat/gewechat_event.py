import random
import asyncio
from astrbot.core.utils.io import download_image_by_url
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata
from astrbot.api.message_components import Plain, Image
from .client import SimpleGewechatClient

class GewechatPlatformEvent(AstrMessageEvent):
    def __init__(
            self, 
            message_str: str, 
            message_obj: AstrBotMessage, 
            platform_meta: PlatformMetadata, 
            session_id: str,
            client: SimpleGewechatClient
        ):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.client = client
        
    @staticmethod
    async def send_with_client(message: MessageChain, user_name: str):
        pass
                
        
    async def send(self, message: MessageChain):
        to_wxid = self.message_obj.raw_message.get('to_wxid', None)
        
        if not to_wxid:
            logger.error("无法获取到 to_wxid。")
            return
        
        for comp in message.chain:
            if isinstance(comp, Plain):
                await self.client.post_text(to_wxid, comp.text)
        
        await super().send(message)