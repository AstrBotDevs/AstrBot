import abc
from typing import Union, Any, List
from nakuru.entities.components import Plain, At, Image, BaseMessageComponent
from type.astrbot_message import AstrBotMessage
from type.command import CommandResult
from type.astrbot_message import MessageType


class Platform():
    def __init__(self, platform_name: str, context) -> None:
        self.PLATFORM_NAME = platform_name
        self.context = context

    @abc.abstractmethod
    async def handle_msg(self, message: AstrBotMessage):
        '''
        处理到来的消息
        '''
        pass

    @abc.abstractmethod
    async def reply_msg(self, message: AstrBotMessage, 
                        result_message: List[BaseMessageComponent]):
        '''
        回复用户唤醒机器人的消息。（被动回复）
        '''
        pass

    @abc.abstractmethod
    async def send_msg(self, target: Any, result_message: CommandResult):
        '''
        发送消息（主动）
        '''
        pass
    
    @abc.abstractmethod
    async def send_msg_new(self, message_type: MessageType, target: str, result_message: CommandResult):
        '''
        发送消息（主动）
        '''
        pass

    def parse_message_outline(self, message: AstrBotMessage) -> str:
        '''
        将消息解析成大纲消息形式，如: xxxxx[图片]xxxxx。用于输出日志等。
        '''
        if isinstance(message, str):
            return message
        ret = ''
        parsed = message if isinstance(message, list) else message.message
        try:
            for node in parsed:
                if isinstance(node, Plain):
                    ret += node.text.replace('\n', ' ')
                elif isinstance(node, At):
                    ret += f'[At: {node.name}/{node.qq}]'
                elif isinstance(node, Image):
                    ret += '[图片]'
        except Exception as e:
            pass
        return ret[:100] if len(ret) > 100 else ret
    
    def check_nick(self, message_str: str) -> bool:
        w = self.context.config_helper.wake_prefix
        if not w: return False
        for nick in w:
            if nick and message_str.strip().startswith(nick):
                return True
        return False

    async def convert_to_t2i_chain(self, message_result: list) -> list:
        plain_str = ""
        rendered_images = []
        for i in message_result:
            if isinstance(i, Plain):
                plain_str += i.text
        if plain_str and len(plain_str) > 50:
            p = await self.context.image_renderer.render(plain_str, return_url=True)
            if p.startswith('http'):
                rendered_images.append(Image.fromURL(p))
            else:
                rendered_images.append(Image.fromFileSystem(p))
            return rendered_images
        
    async def record_metrics(self):
        self.context.metrics_uploader.increment_platform_stat(self.PLATFORM_NAME)