import time
from dataclasses import dataclass

from astrbot.core.message.components import BaseMessageComponent

from .message_type import MessageType


@dataclass
class MessageMember:
    user_id: str  # 发送者id
    nickname: str | None = None

    def __str__(self) -> str:
        # 使用 f-string 来构建返回的字符串表示形式
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

    def __str__(self) -> str:
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
    """Represents a message received from the platform, after parsing and normalization.
    This is the main message object that will be passed to plugins and handlers."""

    type: MessageType
    """GroupMessage, FriendMessage, etc"""
    self_id: str
    """Bot's ID"""
    session_id: str
    """Session ID, which is the last part of UMO"""
    message_id: str
    """Message ID"""
    group: Group | None
    """The group info, None if it's a friend message"""
    sender: MessageMember
    """The sender info"""
    message: list[BaseMessageComponent]
    """Sorted list of message components after parsing"""
    message_str: str
    """The parsed message text after parsing, without any formatting or special components"""
    raw_message: object
    """The raw message object, the specific type depends on the platform"""
    timestamp: int
    """The timestamp when the message is received, in seconds"""

    def __init__(self) -> None:
        self.timestamp = int(time.time())
        self.group = None

    def __str__(self) -> str:
        return str(self.__dict__)

    @property
    def group_id(self) -> str:
        if self.group:
            return self.group.group_id
        return ""

    @group_id.setter
    def group_id(self, value: str | None) -> None:
        if value:
            if self.group:
                self.group.group_id = value
            else:
                self.group = Group(group_id=value)
        else:
            self.group = None
