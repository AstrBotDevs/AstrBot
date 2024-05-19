from enum import Enum
from typing import List
from dataclasses import dataclass
from nakuru.entities.components import BaseMessageComponent

from type.register import RegisteredPlatform
from type.types import GlobalObject

class MessageType(Enum):
    GROUP_MESSAGE = 'GroupMessage'  # 群组形式的消息
    FRIEND_MESSAGE = 'FriendMessage'  # 私聊、好友等单聊消息
    GUILD_MESSAGE = 'GuildMessage'  # 频道消息


@dataclass
class MessageMember():
    user_id: str  # 发送者id
    nickname: str = None


class AstrBotMessage():
    '''
    AstrBot 的消息对象
    '''
    tag: str  # 消息来源标签
    type: MessageType  # 消息类型
    self_id: str  # 机器人的识别id
    session_id: str  # 会话id
    message_id: str  # 消息id
    sender: MessageMember  # 发送者
    message: List[BaseMessageComponent]  # 消息链使用 Nakuru 的消息链格式
    message_str: str  # 最直观的纯文本消息字符串
    raw_message: object
    timestamp: int  # 消息时间戳

    def __str__(self) -> str:
        return str(self.__dict__)

class AstrMessageEvent():
    '''
    消息事件。
    '''
    context: GlobalObject  # 一些公用数据
    message_str: str  # 纯消息字符串
    message_obj: AstrBotMessage  # 消息对象
    platform: RegisteredPlatform  # 来源平台
    role: str  # 基本身份。`admin` 或 `member`
    session_id: int  # 会话 id

    def __init__(self,
                 message_str: str,
                 message_obj: AstrBotMessage,
                 platform: RegisteredPlatform,
                 role: str,
                 context: GlobalObject,
                 session_id: str = None):
        self.context = context
        self.message_str = message_str
        self.message_obj = message_obj
        self.platform = platform
        self.role = role
        self.session_id = session_id
