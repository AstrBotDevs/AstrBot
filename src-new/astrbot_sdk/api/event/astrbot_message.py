"""旧版消息对象兼容类型。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..message.components import BaseMessageComponent
from .message_type import MessageType


@dataclass(slots=True)
class MessageMember:
    user_id: str
    nickname: str | None = None


@dataclass(slots=True)
class Group:
    group_id: str
    group_name: str | None = None
    group_avatar: str | None = None
    group_owner: str | None = None
    group_admins: list[str] | None = None
    members: list[MessageMember] | None = None


@dataclass(slots=True)
class AstrBotMessage:
    type: MessageType
    self_id: str
    session_id: str
    message_id: str
    sender: MessageMember
    message: list[BaseMessageComponent] = field(default_factory=list)
    message_str: str = ""
    raw_message: dict = field(default_factory=dict)
    timestamp: int = field(default_factory=lambda: int(time.time()))
    group: Group | None = None

    @property
    def group_id(self) -> str:
        if self.group is None:
            return ""
        return self.group.group_id

    @group_id.setter
    def group_id(self, value: str) -> None:
        if value:
            if self.group is None:
                self.group = Group(group_id=value)
            else:
                self.group.group_id = value
            return
        self.group = None
