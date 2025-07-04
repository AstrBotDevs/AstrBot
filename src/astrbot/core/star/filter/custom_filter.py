from abc import abstractmethod, ABCMeta

from . import HandlerFilter
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.config import AstrBotConfig


class CustomFilterMeta(ABCMeta):
    def __and__(cls, other):
        if not issubclass(other, CustomFilter):
            raise TypeError("Operands must be subclasses of CustomFilter.")
        return CustomFilterAnd(cls(), other())

    def __or__(cls, other):
        if not issubclass(other, CustomFilter):
            raise TypeError("Operands must be subclasses of CustomFilter.")
        return CustomFilterOr(cls(), other())


class CustomFilter(HandlerFilter, metaclass=CustomFilterMeta):
    def __init__(self, raise_error: bool = True, **kwargs):
        self.raise_error = raise_error

    @abstractmethod
    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        """一个用于重写的自定义Filter"""
        raise NotImplementedError

    def __or__(self, other):
        return CustomFilterOr(self, other)

    def __and__(self, other):
        return CustomFilterAnd(self, other)


class CustomFilterOr(CustomFilter):
    def __init__(self, filter1: CustomFilter, filter2: CustomFilter):
        super().__init__()
        if not isinstance(filter1, (CustomFilter, CustomFilterAnd, CustomFilterOr)):
            raise ValueError(
                "CustomFilter lass can only operate with other CustomFilter."
            )
        self.filter1 = filter1
        self.filter2 = filter2

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        return self.filter1.filter(event, cfg) or self.filter2.filter(event, cfg)


class CustomFilterAnd(CustomFilter):
    def __init__(self, filter1: CustomFilter, filter2: CustomFilter):
        super().__init__()
        if not isinstance(filter1, (CustomFilter, CustomFilterAnd, CustomFilterOr)):
            raise ValueError(
                "CustomFilter lass can only operate with other CustomFilter."
            )
        self.filter1 = filter1
        self.filter2 = filter2

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        return self.filter1.filter(event, cfg) and self.filter2.filter(event, cfg)
