"""SDK-visible message session identifier.

本模块定义 MessageSession 类，用于统一表示消息会话标识符。
会话标识符格式为：platform_id:message_type:session_id

例如：
- qq:group:123456 表示 QQ 群 123456
- wechat:private:user789 表示微信私聊用户 user789

该格式与 AstrBot 核心的 unified_msg_origin 保持兼容，
确保 SDK 与核心之间的会话信息能够正确传递。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MessageSession:
    """SDK-visible message session identifier.

    The string form stays compatible with AstrBot's unified message origin:
    ``platform_id:message_type:session_id``.
    """

    platform_id: str
    message_type: str
    session_id: str

    def __post_init__(self) -> None:
        self.platform_id = str(self.platform_id)
        self.message_type = str(self.message_type).lower()
        self.session_id = str(self.session_id)

    def __str__(self) -> str:
        return f"{self.platform_id}:{self.message_type}:{self.session_id}"

    @classmethod
    def from_str(cls, session: str) -> MessageSession:
        platform_id, message_type, session_id = str(session).split(":", 2)
        return cls(
            platform_id=platform_id,
            message_type=message_type,
            session_id=session_id,
        )
