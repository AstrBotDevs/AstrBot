import abc
from typing import Tuple


class ContentSafetyStrategy(abc.ABC):
    @abc.abstractmethod
    def check(self, content: str) -> Tuple[bool, str]:
        raise NotImplementedError
