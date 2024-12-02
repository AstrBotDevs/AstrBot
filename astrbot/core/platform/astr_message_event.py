import abc
from dataclasses import dataclass
from .astrbot_message import AstrBotMessage
from .platform_metadata import PlatformMetadata
from astrbot.core.message.message_event_result import MessageEventResult, MessageChain
from astrbot.core.platform.message_type import MessageType
from typing import List
from astrbot.core.message.components import BaseMessageComponent, Plain, Image
from astrbot.core.utils.metrics import Metric

@dataclass
class MessageSesion:
    platform_name: str
    message_type: MessageType
    session_id: str
    
    def __str__(self):
        return f"{self.platform_name}:{self.message_type.value}:{self.session_id}"
    
    @staticmethod
    def from_str(session_str: str):
        platform_name, message_type, session_id = session_str.split(":")
        return MessageSesion(platform_name, MessageType(message_type), session_id)

class AstrMessageEvent(abc.ABC):
    def __init__(self, 
                message_str: str,
                message_obj: AstrBotMessage,
                platform_meta: PlatformMetadata,
                session_id: str,):
        self.message_str = message_str
        self.message_obj = message_obj
        self.platform_meta = platform_meta
        self.session_id = session_id
        self.role = "member"
        self.is_wake = False
        
        self._result: MessageEventResult = None
        self._extras = {}
        self.session = MessageSesion(
            platform_name=platform_meta.name,
            message_type=message_obj.type,
            session_id=session_id
        )
        self.unified_msg_origin = str(self.session)
    
    def get_platform_name(self):
        return self.platform_meta.name
    
    def get_message_str(self) -> str:
        '''
        获取消息字符串。
        '''
        return self.message_str
    
    def _outline_chain(self, chain: List[BaseMessageComponent]) -> str:
        outline = ""
        for i in chain:
            if isinstance(i, Plain):
                outline += i.text
            if isinstance(i, Image):
                outline += "[图片]"
        return outline
    
    def get_message_outline(self) -> str:
        '''
        获取消息概要。
        
        除了文本消息外，其他消息类型会被转换为对应的占位符。如图片消息会被转换为 [图片]。
        '''
        return self._outline_chain(self.message_obj.message)
    
    def get_messages(self) -> List[BaseMessageComponent]:
        '''
        获取消息链。
        '''
        return self.message_obj.message
    
    def get_session_id(self) -> str:
        '''
        获取会话id。
        '''
        return self.session_id
    
    def get_self_id(self) -> str:
        '''
        获取机器人自身的id。
        '''
        return self.message_obj.self_id
    
    def get_sender_id(self) -> str:
        '''
        获取消息发送者的id。
        '''
        return self.message_obj.sender.user_id
    
    def get_sender_name(self) -> str:
        '''
        获取消息发送者的名称。(可能会返回空字符串)
        '''
        return self.message_obj.sender.nickname
        
    def set_result(self, result: MessageEventResult):
        '''
        设置消息事件的结果。当设置了结果后，消息事件将不再继续传递。
        '''
        self._result = result
        
    def get_result(self) -> MessageEventResult:
        '''
        获取消息事件的结果。
        '''
        return self._result
        
    def set_extra(self, key, value):
        '''
        设置额外的信息。
        '''
        self._extras[key] = value
        
    def is_private_chat(self) -> bool:
        '''
        是否是私聊。
        '''
        return self.message_obj.type.value == (MessageType.FRIEND_MESSAGE).value
    
    def is_wake_up(self) -> bool:
        '''
        是否是唤醒机器人的事件。
        
        机器人被唤醒的条件：
        1. 消息以用户设置的唤醒前缀开头，默认是 `/`.
        2. 消息中有 at 机器人的消息。
        3. 是私聊。
        '''
        return self.is_wake
    
    async def send(self, message: MessageChain):
        '''
        发送消息到消息平台。
        '''
        await Metric.upload(msg_event_tick = 1, adapter_name = self.platform_meta.name)