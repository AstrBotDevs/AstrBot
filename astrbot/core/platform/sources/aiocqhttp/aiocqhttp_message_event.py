import os
import random
import asyncio

from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Plain, Image
from aiocqhttp import CQHttp
from astrbot.core.utils.io import file_to_base64, download_image_by_url

class AiocqhttpMessageEvent(AstrMessageEvent):
    def __init__(self, message_str, message_obj, platform_meta, session_id, bot: CQHttp):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.bot = bot
    
    @staticmethod
    async def _parse_onebot_json(message_chain: MessageChain):
        '''解析成 OneBot json 格式'''
        ret = []
        for segment in message_chain.chain:
            d = segment.toDict()
            if isinstance(segment, Plain):
                d['type'] = 'text'
            if isinstance(segment, Image):
                # convert to base64
                if segment.file and segment.file.startswith("file:///"):
                    image_base64 = file_to_base64(segment.file[8:])
                    image_file_path = segment.file[8:]
                elif segment.file and segment.file.startswith("http"):
                    image_file_path = await download_image_by_url(segment.file)
                    image_base64 = file_to_base64(image_file_path)
                d['data'] = {
                    'file': image_base64,
                }
            ret.append(d)
        return ret

    async def send(self, message: MessageChain):
        ret = await AiocqhttpMessageEvent._parse_onebot_json(message)
        if os.environ.get('TEST_MODE', 'off') == 'on':
            return
        
        if message.is_split_: # 分条发送
            for m in ret:
                await self.bot.send(self.message_obj.raw_message, [m])
                await asyncio.sleep(random.uniform(0.75, 2.5))
        else:
            await self.bot.send(self.message_obj.raw_message, ret)
        await super().send(message)