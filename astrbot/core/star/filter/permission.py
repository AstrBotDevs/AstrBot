from astrbot.core.config import AstrBotConfig
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from . import HandlerFilter


class ActionPermissionFilter(HandlerFilter):
    """Declarative action gate resolved asynchronously by the pipeline."""

    def __init__(self, action: str, raise_error: bool = True) -> None:
        if not isinstance(action, str) or not action:
            raise ValueError("Authorization action must be a non-empty string")
        self.action = action
        self.raise_error = raise_error

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        """Fail closed for synchronous callers outside the pipeline."""

        del event, cfg
        return False
