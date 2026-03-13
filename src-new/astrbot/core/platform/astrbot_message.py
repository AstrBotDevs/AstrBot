"""旧版 ``astrbot.core.platform.astrbot_message`` 导入路径兼容入口。"""

from astrbot_sdk.api.event import AstrBotMessage, Group, MessageMember, MessageType

__all__ = ["AstrBotMessage", "Group", "MessageMember", "MessageType"]
