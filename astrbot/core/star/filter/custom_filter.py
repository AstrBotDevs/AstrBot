from abc import abstractmethod

from . import HandlerFilter
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.config import AstrBotConfig

class CustomFilter(HandlerFilter):
    def __init__(self,  raise_error: bool = True):
        self.raise_error = raise_error

    @abstractmethod
    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        ''' 一个用于重写的自定义Filter '''
        raise NotImplementedError
