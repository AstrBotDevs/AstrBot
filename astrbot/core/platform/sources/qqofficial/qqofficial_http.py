from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import aiohttp
from botpy.errors import HttpErrorDict, ServerError
from botpy.http import BotHttp, Route

from astrbot.api import logger
from astrbot.utils.http_ssl_common import build_ssl_context_with_certifi

_CONNECTION_LIMIT = 32
_CONNECTION_LIMIT_PER_HOST = 16
_MAX_CONCURRENT_REQUESTS = 16
_MAX_PENDING_REQUESTS = 64
_QUEUE_TIMEOUT_SECONDS = 5.0
_SUCCESS_STATUS_CODES = {200, 202, 204}


async def _parse_response(response: aiohttp.ClientResponse) -> Any:
    """Parse one QQ API response using qq-botpy's status-to-error mapping.

    Args:
        response: Completed aiohttp response.

    Returns:
        Parsed JSON or text response payload.

    Raises:
        RuntimeError: The QQ API returns a non-success status.
    """
    content_type = response.headers.get("content-type")
    if not content_type:
        data = None
    else:
        try:
            data = (
                await response.json()
                if content_type.startswith("application/json")
                else await response.text()
            )
        except ValueError:
            data = None

    if response.status in _SUCCESS_STATUS_CODES:
        return data

    message = data.get("message") if isinstance(data, dict) else str(data)
    error_type = HttpErrorDict.get(response.status, ServerError)
    raise error_type(msg=message) from None


class QQOfficialHttpClosedError(RuntimeError):
    """Raised when an outbound request starts after adapter shutdown."""


class QQOfficialHttpOverloadedError(RuntimeError):
    """Raised when the bounded outbound request queue is full or times out."""


class QQOfficialHttp(BotHttp):
    """QQ Bot HTTP transport with reusable connections and bounded concurrency.

    Args:
        timeout: Total timeout in seconds for one HTTP attempt.
        is_sandbox: Whether to use QQ's sandbox endpoint.
        app_id: Optional QQ bot application ID.
        secret: Optional QQ bot secret.
        max_concurrent_requests: Maximum active HTTP attempts for one bot.
        max_pending_requests: Maximum active and queued attempts for one bot.
        queue_timeout: Maximum seconds a request may wait for an execution slot.
    """

    def __init__(
        self,
        timeout: int,
        is_sandbox: bool = False,
        app_id: str | None = None,
        secret: str | None = None,
        *,
        max_concurrent_requests: int = _MAX_CONCURRENT_REQUESTS,
        max_pending_requests: int = _MAX_PENDING_REQUESTS,
        queue_timeout: float = _QUEUE_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(
            timeout=timeout,
            is_sandbox=is_sandbox,
            app_id=app_id,
            secret=secret,
        )
        if max_concurrent_requests <= 0:
            raise ValueError("max_concurrent_requests must be positive")
        if max_pending_requests < max_concurrent_requests:
            raise ValueError(
                "max_pending_requests must be greater than or equal to "
                "max_concurrent_requests"
            )
        if queue_timeout <= 0:
            raise ValueError("queue_timeout must be positive")

        self._closing = False
        self._session_lock = asyncio.Lock()
        self._pending_lock = asyncio.Lock()
        self._request_slots = asyncio.Semaphore(max_concurrent_requests)
        self._max_pending_requests = max_pending_requests
        self._queue_timeout = queue_timeout
        self._pending_requests = 0
        self._request_tasks: set[asyncio.Task[Any]] = set()

    def _ensure_open(self) -> None:
        """Reject new work after transport shutdown begins.

        Raises:
            QQOfficialHttpClosedError: The adapter is shutting down.
        """
        if self._closing:
            raise QQOfficialHttpClosedError("QQ Official HTTP transport is closed")

    async def check_session(self) -> None:
        """Refresh authorization and create one reusable HTTP session if needed.

        Raises:
            QQOfficialHttpClosedError: The adapter is shutting down.
            RuntimeError: The QQ bot token is not initialized.
        """
        self._ensure_open()
        if self._token is None:
            raise RuntimeError("QQ Official HTTP token is not initialized")

        async with self._session_lock:
            self._ensure_open()
            await self._token.check_token()
            self._ensure_open()
            self._headers = {
                "Authorization": self._token.get_string(),
                "X-Union-Appid": self._token.app_id,
            }
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(
                        limit=_CONNECTION_LIMIT,
                        limit_per_host=_CONNECTION_LIMIT_PER_HOST,
                        ssl=build_ssl_context_with_certifi(),
                        keepalive_timeout=30,
                        ttl_dns_cache=300,
                    )
                )

    @asynccontextmanager
    async def request_slot(self) -> AsyncIterator[None]:
        """Reserve one bounded outbound request slot.

        Yields:
            Control while the caller owns a request slot.

        Raises:
            QQOfficialHttpClosedError: The adapter is shutting down.
            QQOfficialHttpOverloadedError: The queue is full or its wait times out.
        """
        self._ensure_open()

        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("QQ Official HTTP request requires an asyncio task")
        self._request_tasks.add(task)

        counted = False
        acquired = False
        try:
            async with self._pending_lock:
                if self._pending_requests >= self._max_pending_requests:
                    raise QQOfficialHttpOverloadedError(
                        "QQ Official outbound request queue is full"
                    )
                self._pending_requests += 1
                counted = True

            try:
                await asyncio.wait_for(
                    self._request_slots.acquire(),
                    timeout=self._queue_timeout,
                )
                acquired = True
            except asyncio.TimeoutError as exc:
                raise QQOfficialHttpOverloadedError(
                    "QQ Official outbound request queue timed out"
                ) from exc

            self._ensure_open()
            yield
        finally:
            if acquired:
                self._request_slots.release()
            if counted:
                async with self._pending_lock:
                    self._pending_requests -= 1
            self._request_tasks.discard(task)

    async def request(self, route: Route, retry_time: int = 0, **kwargs: Any) -> Any:
        """Execute one HTTP attempt without qq-botpy's nested retry loop.

        Args:
            route: QQ API route.
            retry_time: Unused qq-botpy compatibility argument.
            **kwargs: Arguments forwarded to ``aiohttp.ClientSession.request``.

        Returns:
            Parsed QQ API response.

        Raises:
            QQOfficialHttpClosedError: The adapter is shutting down.
            QQOfficialHttpOverloadedError: The outbound queue is overloaded.
            aiohttp.ClientError: The HTTP attempt fails.
            TimeoutError: The HTTP attempt times out.
        """
        del retry_time
        if "json" in kwargs:
            json_payload = kwargs["json"]
            file_image = json_payload.get("file_image")
            if file_image and isinstance(file_image, bytes):
                form_data = aiohttp.FormData()
                for key, value in kwargs.pop("json").items():
                    if not value or isinstance(value, dict):
                        continue
                    form_data.add_field(key, value)
                kwargs["data"] = form_data

        async with self.request_slot():
            await self.check_session()
            route.is_sandbox = self.is_sandbox
            session = self._session
            if session is None:
                raise RuntimeError("QQ Official HTTP session is unavailable")

            try:
                async with session.request(
                    method=route.method,
                    url=route.url,
                    headers=self._headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    **kwargs,
                ) as response:
                    return await _parse_response(response)
            except asyncio.TimeoutError:
                logger.warning(
                    "[QQOfficial] HTTP request timed out: method=%s route=%s",
                    route.method,
                    route.path,
                )
                raise
            except ConnectionResetError:
                logger.warning(
                    "[QQOfficial] HTTP connection reset: method=%s route=%s",
                    route.method,
                    route.path,
                )
                raise

    async def close(self) -> None:
        """Stop queued/in-flight requests and permanently close the transport."""
        if self._closing:
            return
        self._closing = True

        current_task = asyncio.current_task()
        request_tasks = [
            task
            for task in self._request_tasks
            if task is not current_task and not task.done()
        ]
        for task in request_tasks:
            task.cancel()
        if request_tasks:
            await asyncio.gather(*request_tasks, return_exceptions=True)

        async with self._session_lock:
            session = self._session
            self._session = None
            if session is not None and not session.closed:
                await session.close()
