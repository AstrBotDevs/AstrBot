import abc
from typing import Tuple


class ContentSafetyStrategy(abc.ABC):
    @abc.abstractmethod
    def check(self, content: str) -> tuple[bool, str]:
        raise NotImplementedError
