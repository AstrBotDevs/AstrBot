from astrbot.core.platform.message_type import MessageType
from dataclasses import dataclass


@dataclass
class MessageSession:
    """描述一条消息在 AstrBot 中对应的会话的唯一标识。
    如果您需要实例化 MessageSession，请不要给 platform_id 赋值（或者同时给 platform_name 和 platform_id 赋值相同值）。它会在 __post_init__ 中自动设置为 platform_name 的值。"""

    platform_name: str
    """平台适配器实例的唯一标识符。自 AstrBot v4.0.0 起，该字段实际为 platform_id。"""
    message_type: MessageType
    session_id: str
    platform_id: str = None

    def __str__(self):
        return f"{self.platform_id}:{self.message_type.value}:{self.session_id}"

    def __post_init__(self):
        self.platform_id = self.platform_name

    @staticmethod
    def from_str(session_str: str):
        platform_id, message_type, session_id = session_str.split(":")
        return MessageSession(platform_id, MessageType(message_type), session_id)


MessageSesion = MessageSession  # back compatibility
