import asyncio

from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Plain, Image, Record, At, Node, Music, Video
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
            elif isinstance(segment, (Image, Record)):
                # convert to base64
                if segment.file and segment.file.startswith("file:///"):
                    bs64_data = file_to_base64(segment.file[8:])
                    image_file_path = segment.file[8:]
                elif segment.file and segment.file.startswith("http"):
                    image_file_path = await download_image_by_url(segment.file)
                    bs64_data = file_to_base64(image_file_path)
                elif segment.file and segment.file.startswith("base64://"):
                    bs64_data = segment.file
                else:
                    bs64_data = file_to_base64(segment.file)
                d['data'] = {
                    'file': bs64_data,
                }
            elif isinstance(segment, At):
                d['data'] = {
                    'qq': str(segment.qq) # 转换为字符串
                }
            ret.append(d)
        return ret

    async def send(self, message: MessageChain):
        ret = await AiocqhttpMessageEvent._parse_onebot_json(message)
        
        send_one_by_one = False
        for seg in message.chain:
            if isinstance(seg, (Node, Music)):
                # 转发消息不能和普通消息混在一起发送
                send_one_by_one = True
                break
        
        if send_one_by_one:
            for seg in message.chain:
                await self.bot.send(self.message_obj.raw_message, await AiocqhttpMessageEvent._parse_onebot_json(MessageChain([seg])))
                await asyncio.sleep(0.5)
        else:
            await self.bot.send(self.message_obj.raw_message, ret)
        
        await super().send(message)