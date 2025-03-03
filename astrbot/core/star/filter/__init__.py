import abc
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.config import AstrBotConfig


class HandlerFilter(abc.ABC):
    @abc.abstractmethod
    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        """是否应当被过滤"""
        raise NotImplementedError


__all__ = ["HandlerFilter", "MessageType", "AstrMessageEvent", "AstrBotConfig"]
