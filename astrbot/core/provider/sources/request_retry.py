from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from contextvars import ContextVar
from typing import TypeVar

from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from astrbot import logger
from astrbot.core.utils.config_number import coerce_int_config
from astrbot.core.utils.network_utils import is_connection_error

T = TypeVar("T")

REQUEST_RETRY_ATTEMPTS = 5  # default value
REQUEST_RETRY_WAIT_MIN_S = 0.2
REQUEST_RETRY_WAIT_MAX_S = 30
REQUEST_RETRY_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504, 529}
provider_retry_rate_limits: ContextVar[bool] = ContextVar(
    "provider_retry_rate_limits",
    default=True,
)
provider_oauth_web_search: ContextVar[str] = ContextVar(
    "provider_oauth_web_search",
    default="inherit",
)


class ProviderRequestError(RuntimeError):
    """Provider failure with a machine-readable HTTP status code."""

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def get_provider_request_status_code(error: BaseException) -> int | None:
    for attr in ("status_code", "status", "code"):
        value = getattr(error, attr, None)
        if isinstance(value, int):
            return value

    response = getattr(error, "response", None)
    if response is not None:
        status_code = getattr(response, "status_code", None)
        if isinstance(status_code, int):
            return status_code

    return None


def _is_retryable_provider_request_error(
    error: BaseException,
    *,
    retry_rate_limits: bool,
) -> bool:
    status_code = get_provider_request_status_code(error)
    if status_code == 429 and not retry_rate_limits:
        return False

    if is_connection_error(error):
        return True

    error_type_name = type(error).__name__
    if error_type_name in {"APIConnectionError", "APITimeoutError"}:
        return True

    if status_code is None:
        return False

    return status_code in REQUEST_RETRY_STATUS_CODES or 500 <= status_code <= 599


def _log_retry(
    provider_label: str,
    retry_state: RetryCallState,
    max_attempts: int,
) -> None:
    error = retry_state.outcome.exception() if retry_state.outcome else None
    logger.warning(
        f"[{provider_label}] Request failed with retryable error; "
        f"retrying ({retry_state.attempt_number + 1}/{max_attempts}): "
        f"{error}"
    )


def _build_retrying(
    provider_label: str,
    *,
    retry_rate_limits: bool,
    max_attempts: int | None = None,
) -> AsyncRetrying:
    max_attempts = coerce_int_config(
        max_attempts if max_attempts is not None else REQUEST_RETRY_ATTEMPTS,
        default=REQUEST_RETRY_ATTEMPTS,
        min_value=1,
        field_name="request_max_retries",
        source=provider_label,
    )

    return AsyncRetrying(
        retry=retry_if_exception(
            lambda error: _is_retryable_provider_request_error(
                error,
                retry_rate_limits=retry_rate_limits,
            )
        ),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(
            multiplier=1,
            min=REQUEST_RETRY_WAIT_MIN_S,
            max=REQUEST_RETRY_WAIT_MAX_S,
        ),
        before_sleep=lambda retry_state: _log_retry(
            provider_label,
            retry_state,
            max_attempts,
        ),
        reraise=True,
    )


async def retry_provider_request(
    provider_label: str,
    request_factory: Callable[[], Awaitable[T]],
    *,
    retry_rate_limits: bool | None = None,
    max_attempts: int | None = None,
) -> T:
    effective_retry_rate_limits = (
        provider_retry_rate_limits.get()
        if retry_rate_limits is None
        else retry_rate_limits
    )
    retrying = _build_retrying(
        provider_label,
        retry_rate_limits=effective_retry_rate_limits,
        max_attempts=max_attempts,
    )

    async for attempt in retrying:
        with attempt:
            return await request_factory()

    raise RuntimeError("Provider request retry loop exited unexpectedly.")


@asynccontextmanager
async def retry_provider_request_context(
    provider_label: str,
    context_manager_factory: Callable[[], AbstractAsyncContextManager[T]],
    *,
    retry_rate_limits: bool | None = None,
    max_attempts: int | None = None,
) -> AsyncIterator[T]:
    manager: AbstractAsyncContextManager[T] | None = None

    async def _enter_context() -> T:
        nonlocal manager
        manager = context_manager_factory()
        return await manager.__aenter__()

    value = await retry_provider_request(
        provider_label,
        _enter_context,
        retry_rate_limits=retry_rate_limits,
        max_attempts=max_attempts,
    )

    if manager is None:
        raise RuntimeError("Provider request context was not created.")

    try:
        yield value
    except BaseException as error:
        if await manager.__aexit__(type(error), error, error.__traceback__):
            return
        raise
    else:
        await manager.__aexit__(None, None, None)
