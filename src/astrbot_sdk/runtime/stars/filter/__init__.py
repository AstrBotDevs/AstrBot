import abc

from ....api.basic.astrbot_config import AstrBotConfig
from ....api.event import AstrMessageEvent


class HandlerFilter(abc.ABC):
    @abc.abstractmethod
    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        """是否应当被过滤"""
        raise NotImplementedError


__all__ = ["AstrBotConfig", "AstrMessageEvent", "HandlerFilter"]
