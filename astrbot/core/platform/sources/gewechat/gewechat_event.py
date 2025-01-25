import random
import asyncio
import os
from astrbot.core.utils.io import save_temp_img, download_image_by_url
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
            elif isinstance(comp, Image):
                img_url = comp.file
                img_path = ""
                if img_url.startswith("file:///"):
                    with open(comp.file[8:], "rb") as f:
                        img_path = save_temp_img(f.read())
                elif comp.file and comp.file.startswith("http"):
                    img_path = await download_image_by_url(comp.file)
                    
                if not img_path:
                    logger.error("无法获取到图片路径。")
                    return

                file_id = os.path.basename(img_path).split(".")[0]
                img_url = f"{self.client.file_server_url}/{file_id}"
                logger.debug(f"gewe callback img url: {img_url}")
                await self.client.post_image(to_wxid, img_url)
        
        await super().send(message)