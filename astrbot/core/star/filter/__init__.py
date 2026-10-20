import abc

from astrbot.core.config import AstrBotConfig
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_type import MessageType


class HandlerFilter(abc.ABC):
    @abc.abstractmethod
    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        """是否应当被过滤"""
        raise NotImplementedError


__all__ = ["AstrBotConfig", "AstrMessageEvent", "HandlerFilter", "MessageType"]
