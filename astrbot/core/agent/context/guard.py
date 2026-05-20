from ..message import Message
from .config import ContextConfig
from .manager import ContextManager


class RequestContextGuard:
    """Request-time context guard before sending messages to a provider.

    This guard is intentionally scoped to a single provider request. It may
    truncate or compress the in-flight messages to keep the current request
    within model/provider limits, but it does not own persistent history and
    should not be treated as the memory-layer compactor.
    """

    def __init__(self, config: ContextConfig) -> None:
        self.config = config
        self._manager = ContextManager(config)

    async def process(
        self,
        messages: list[Message],
        trusted_token_usage: int = 0,
    ) -> list[Message]:
        """Apply request-time context guarding to messages."""
        return await self._manager.process(
            messages,
            trusted_token_usage=trusted_token_usage,
        )
