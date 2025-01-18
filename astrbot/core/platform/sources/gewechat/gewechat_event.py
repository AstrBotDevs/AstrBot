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
        # plain = ""
        # for comp in message.chain:
        #     if isinstance(comp, Plain):
        #         if message.is_split_:
        #             await client.send_msg(comp.text, user_name)
        #         else:
        #             plain += comp.text
        #     elif isinstance(comp, Image):
        #         if comp.file and comp.file.startswith("file:///"):
        #             file_path = comp.file.replace("file:///", "")
        #             with open(file_path, "rb") as f:
        #                 await client.send_image(user_name, fd=f)
        #         elif comp.file and comp.file.startswith("http"):
        #             image_path = await download_image_by_url(comp.file)
        #             with open(image_path, "rb") as f:
        #                 await client.send_image(user_name, fd=f)
        #     else:
        #         logger.error(f"不支持的 vchat(微信适配器) 消息类型: {comp}")
        #     await asyncio.sleep(random.uniform(0.5, 1.5)) # 🤓
        
        # if plain:
        #     await client.send_msg(plain, user_name)
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