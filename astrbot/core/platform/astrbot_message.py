import time
from typing import List
from dataclasses import dataclass
from astrbot.core.message.components import BaseMessageComponent
from .message_type import MessageType


@dataclass
class MessageMember:
    user_id: str  # 发送者id
    nickname: str = None

    def __str__(self):
        # 使用 f-string 来构建返回的字符串表示形式
        return (
            f"User ID: {self.user_id},"
            f"Nickname: {self.nickname if self.nickname else 'N/A'}"
        )


@dataclass
class Group:
    group_id: str
    """群号"""
    group_name: str = None
    """群名称"""
    group_avatar: str = None
    """群头像"""
    group_owner: str = None
    """群主 id"""
    group_admins: List[str] = None
    """群管理员 id"""
    members: List[MessageMember] = None
    """所有群成员"""

    def __str__(self):
        # 使用 f-string 来构建返回的字符串表示形式
        return (
            f"Group ID: {self.group_id}\n"
            f"Name: {self.group_name if self.group_name else 'N/A'}\n"
            f"Avatar: {self.group_avatar if self.group_avatar else 'N/A'}\n"
            f"Owner ID: {self.group_owner if self.group_owner else 'N/A'}\n"
            f"Admin IDs: {self.group_admins if self.group_admins else 'N/A'}\n"
            f"Members Len: {len(self.members) if self.members else 0}\n"
            f"First Member: {self.members[0] if self.members else 'N/A'}\n"
        )


class AstrBotMessage:
    """
    AstrBot 的消息对象
    """

    type: MessageType  # 消息类型
    self_id: str  # 机器人的识别id
    session_id: str  # 会话id。取决于 unique_session 的设置。
    message_id: str  # 消息id
    group_id: str = ""  # 群组id，如果为私聊，则为空
    sender: MessageMember  # 发送者
    message: List[BaseMessageComponent]  # 消息链使用 Nakuru 的消息链格式
    message_str: str  # 最直观的纯文本消息字符串
    raw_message: object
    timestamp: int  # 消息时间戳

    def __init__(self) -> None:
        self.timestamp = int(time.time())

    def __str__(self) -> str:
        return str(self.__dict__)
