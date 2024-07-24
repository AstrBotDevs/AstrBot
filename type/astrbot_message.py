import time
from enum import Enum
from typing import List
from dataclasses import dataclass
from nakuru.entities.components import BaseMessageComponent

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
    
    def __init__(self) -> None:
        self.timestamp = int(time.time())

    def __str__(self) -> str:
        return str(self.__dict__)
