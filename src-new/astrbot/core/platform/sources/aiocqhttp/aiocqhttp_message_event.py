"""旧版 aiocqhttp 事件类型的最小导入兼容入口。"""

from astrbot.core.platform.astr_message_event import AstrMessageEvent

AiocqhttpMessageEvent = AstrMessageEvent

__all__ = ["AiocqhttpMessageEvent"]
