"""旧版消息类型兼容枚举。"""

from __future__ import annotations

from enum import Enum


class MessageType(Enum):
    GROUP_MESSAGE = "GroupMessage"
    FRIEND_MESSAGE = "FriendMessage"
    OTHER_MESSAGE = "OtherMessage"
