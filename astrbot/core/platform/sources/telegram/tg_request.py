import asyncio

import httpx
from telegram.error import TimedOut
from telegram.request import HTTPXRequest

from astrbot.api import logger


class TelegramPollingRequest(HTTPXRequest):
    """Detect pool exhaustion hidden by the SDK's timeout retry loop."""

    def __init__(
        self, recovery_requested: asyncio.Event, recovery_threshold: int
    ) -> None:
        """Create a request with the SDK's default polling pool size.

        Args:
            recovery_requested: Event observed by the adapter's recovery loop.
            recovery_threshold: Consecutive pool timeouts needed to request recovery.
        """
        super().__init__(connection_pool_size=1)
        self._recovery_requested = recovery_requested
        self._recovery_threshold = recovery_threshold
        self._consecutive_pool_timeouts = 0

    async def do_request(self, *args, **kwargs) -> tuple[int, bytes]:
        """Forward a request and signal repeated connection pool timeouts.

        Args:
            *args: Positional arguments forwarded to HTTPXRequest.do_request.
            **kwargs: Keyword arguments forwarded to HTTPXRequest.do_request.

        Returns:
            The HTTP status code and response body from the SDK request.

        Raises:
            TimedOut: The original SDK timeout, with its HTTPX cause preserved.
            Exception: Any other request error, unchanged.
        """
        try:
            result = await super().do_request(*args, **kwargs)
        except TimedOut as error:
            # The SDK retries TimedOut without invoking the polling error callback.
            if isinstance(error.__cause__, httpx.PoolTimeout):
                self._consecutive_pool_timeouts += 1
                if (
                    self._consecutive_pool_timeouts == self._recovery_threshold
                    and not self._recovery_requested.is_set()
                ):
                    logger.warning(
                        "Telegram polling encountered %s consecutive pool timeouts; "
                        "scheduling client rebuild.",
                        self._consecutive_pool_timeouts,
                    )
                    self._recovery_requested.set()
            else:
                self._consecutive_pool_timeouts = 0
            raise
        except Exception:
            self._consecutive_pool_timeouts = 0
            raise
        else:
            self._consecutive_pool_timeouts = 0
            return result
