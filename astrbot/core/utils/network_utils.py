"""Network error handling utilities for providers."""

import httpx

from astrbot import logger


def is_connection_error(exc: BaseException) -> bool:
    """Check if an exception is a connection/network related error.

    Uses explicit exception type checking instead of brittle string matching.
    Handles httpx network errors, timeouts, and common Python network exceptions.

    Args:
        exc: The exception to check

    Returns:
        True if the exception is a connection/network error
    """
    # Check for httpx network errors
    if isinstance(
        exc,
        (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
            httpx.NetworkError,
            httpx.ProxyError,
            httpx.RequestError,
        ),
    ):
        return True

    # Check for common Python network errors
    if isinstance(exc, (TimeoutError, OSError, ConnectionError)):
        return True

    # Check the __cause__ chain for wrapped connection errors
    cause = getattr(exc, "__cause__", None)
    if cause is not None and cause is not exc:
        return is_connection_error(cause)

    return False


def log_connection_failure(
    provider_label: str,
    error: Exception,
    proxy: str | None = None,
) -> None:
    """Log a connection failure with proxy information.

    If proxy is not provided, will fallback to check os.environ for
    http_proxy/https_proxy environment variables.

    Args:
        provider_label: The provider name for log prefix (e.g., "OpenAI", "Gemini")
        error: The exception that occurred
        proxy: The proxy address if configured, or None/empty string
    """
    import os

    error_type = type(error).__name__

    # Fallback to environment proxy if not configured
    effective_proxy = proxy
    if not effective_proxy:
        effective_proxy = os.environ.get(
            "http_proxy", os.environ.get("https_proxy", "")
        )

    if effective_proxy:
        logger.error(
            f"[{provider_label}] 网络/代理连接失败 ({error_type})。"
            f"代理地址: {effective_proxy}，错误: {error}"
        )
    else:
        logger.error(
            f"[{provider_label}] 网络连接失败 ({error_type})，未配置代理。错误: {error}"
        )


def create_proxy_client(
    provider_label: str,
    proxy: str | None = None,
) -> httpx.AsyncClient | None:
    """Create an httpx AsyncClient with proxy configuration if provided.

    Note: The caller is responsible for closing the client when done.
    Consider using the client as a context manager or calling aclose() explicitly.

    Args:
        provider_label: The provider name for log prefix (e.g., "OpenAI", "Gemini")
        proxy: The proxy address (e.g., "http://127.0.0.1:7890"), or None/empty

    Returns:
        An httpx.AsyncClient configured with the proxy, or None if no proxy
    """
    if proxy:
        logger.info(f"[{provider_label}] 使用代理: {proxy}")
        return httpx.AsyncClient(proxy=proxy)
    return None
