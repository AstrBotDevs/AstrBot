import abc


class ContentSafetyStrategy(abc.ABC):
    @abc.abstractmethod
    def check(self, content: str, locale: str | None = None) -> tuple[bool, str]:
        raise NotImplementedError
