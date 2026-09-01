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


GROUP_MEMBER_PAGE_LIMIT = 10
GROUP_MEMBER_HARD_CAP = 2000


def group_member_lookup_over_cap(*, pages: int, members: int) -> bool:
    """Return whether member pagination crossed the hard lookup limits.

    Args:
        pages: Pages that would be or have been fetched.
        members: Members that would be or have been collected.

    Returns:
        True when either limit is exceeded and the member list must be omitted.
    """
    return pages > GROUP_MEMBER_PAGE_LIMIT or members > GROUP_MEMBER_HARD_CAP


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
    member_count: int | None = None
    """Total members, available even when the member list is incomplete."""

    def copy(self) -> Group:
        """Return a copy that does not share mutable member collections.

        Returns:
            A new group with copied ``group_admins`` and ``members`` lists.
        """
        return Group(
            group_id=self.group_id,
            group_name=self.group_name,
            group_avatar=self.group_avatar,
            group_owner=self.group_owner,
            group_admins=(
                list(self.group_admins) if self.group_admins is not None else None
            ),
            members=list(self.members) if self.members is not None else None,
            member_count=self.member_count,
        )

    @classmethod
    def from_inbound(cls, current: Group | None, group_id: str) -> Group:
        """Copy inbound group data when the ID matches, otherwise start empty.

        Args:
            current: Group attached to the inbound message, if any.
            group_id: Group identifier being queried.

        Returns:
            A new group object that callers may mutate without changing inbound state.
        """
        if current is not None and current.group_id == group_id:
            return current.copy()
        return cls(group_id=group_id)

    def __str__(self) -> str:
        # 使用 f-string 来构建返回的字符串表示形式
        return (
            f"Group ID: {self.group_id}\n"
            f"Name: {self.group_name if self.group_name else 'N/A'}\n"
            f"Avatar: {self.group_avatar if self.group_avatar else 'N/A'}\n"
            f"Owner ID: {self.group_owner if self.group_owner else 'N/A'}\n"
            f"Admin IDs: {self.group_admins if self.group_admins else 'N/A'}\n"
            f"Member Count: {self.member_count if self.member_count is not None else 'N/A'}\n"
            f"Members Len: {len(self.members) if self.members else 0}\n"
            f"First Member: {self.members[0] if self.members else 'N/A'}\n"
        )


class AstrBotMessage:
    """AstrBot 的消息对象"""

    type: MessageType  # 消息类型
    self_id: str  # 机器人的识别id
    session_id: str  # 会话id。取决于 unique_session 的设置。
    message_id: str  # 消息id
    group: Group | None  # 群组
    sender: MessageMember  # 发送者
    message: list[BaseMessageComponent]  # 消息链使用 Nakuru 的消息链格式
    message_str: str  # 最直观的纯文本消息字符串
    raw_message: object
    timestamp: int  # 消息时间戳
    is_reply: bool
    ref_msg: dict[str, object] | None
    reply_kind: str | None
    quoted_item_type: int | None
    quoted_text: str | None
    reply_to: dict[str, object]

    def __init__(self) -> None:
        self.timestamp = int(time.time())
        self.group = None
        self.is_reply = False
        self.ref_msg = None
        self.reply_kind = None
        self.quoted_item_type = None
        self.quoted_text = None
        self.reply_to = {"matched": False}

    def __str__(self) -> str:
        return str(self.__dict__)

    @property
    def group_id(self) -> str:
        """Return the current group id, or an empty string for private chats."""
        if self.group:
            return self.group.group_id
        return ""

    @group_id.setter
    def group_id(self, value: str | None) -> None:
        """设置 group_id"""
        if value:
            if self.group:
                self.group.group_id = value
            else:
                self.group = Group(group_id=value)
        else:
            self.group = None
