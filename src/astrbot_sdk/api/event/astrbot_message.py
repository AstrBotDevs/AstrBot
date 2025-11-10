import time
from dataclasses import dataclass

from .message_type import MessageType
from ..message.components import BaseMessageComponent


@dataclass
class MessageMember:
    user_id: str
    nickname: str | None = None

    def __str__(self):
        return (
            f"User ID: {self.user_id},"
            f"Nickname: {self.nickname if self.nickname else 'N/A'}"
        )


@dataclass
class Group:
    group_id: str
    """群号"""
    group_name: str | None = None
    """群名称"""
    group_avatar: str | None = None
    """群头像"""
    group_owner: str | None = None
    """群主 id"""
    group_admins: list[str] | None = None
    """群管理员 id"""
    members: list[MessageMember] | None = None
    """所有群成员"""

    def __str__(self):
        return (
            f"Group ID: {self.group_id}\n"
            f"Name: {self.group_name if self.group_name else 'N/A'}\n"
            f"Avatar: {self.group_avatar if self.group_avatar else 'N/A'}\n"
            f"Owner ID: {self.group_owner if self.group_owner else 'N/A'}\n"
            f"Admin IDs: {self.group_admins if self.group_admins else 'N/A'}\n"
            f"Members Len: {len(self.members) if self.members else 0}\n"
            f"First Member: {self.members[0] if self.members else 'N/A'}\n"
        )


@dataclass
class AstrBotMessage:
    """AstrBot 的消息对象"""

    type: MessageType
    """消息类型"""
    self_id: str
    """机器人自身 ID"""
    session_id: str
    """会话 ID"""
    message_id: str
    """消息 ID"""
    sender: MessageMember
    """发送者"""
    message: list[BaseMessageComponent]
    """消息链组件列表"""
    message_str: str
    """纯文本消息字符串"""
    raw_message: dict
    """原始消息对象"""
    timestamp: int
    """消息时间戳"""
    group: Group | None = None
    """群信息，如果是私聊则为 None"""

    def __init__(self, **kwargs) -> None:
        self.timestamp = int(time.time())
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __str__(self) -> str:
        return str(self.__dict__)

    @property
    def group_id(self) -> str:
        """向后兼容的 group_id 属性
        群组id，如果为私聊，则为空
        """
        if self.group:
            return self.group.group_id
        return ""

    @group_id.setter
    def group_id(self, value: str):
        """设置 group_id"""
        if value:
            if self.group:
                self.group.group_id = value
            else:
                self.group = Group(group_id=value)
        else:
            self.group = None
