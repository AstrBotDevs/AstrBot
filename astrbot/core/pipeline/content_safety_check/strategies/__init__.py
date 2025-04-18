import abc
# from typing import Tuple 被弃用，需改为 tuple

class ContentSafetyStrategy(abc.ABC):
    @abc.abstractmethod
    def check(self, content: str) -> tuple[bool, str]:
        raise NotImplementedError
