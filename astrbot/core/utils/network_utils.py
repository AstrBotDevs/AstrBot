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
        logger.error(f"[{provider_label}] 网络连接失败 ({error_type})。错误: {error}")


def _is_socks_proxy(proxy: str) -> bool:
    """Check if the proxy URL is a SOCKS proxy.

    Args:
        proxy: The proxy URL string

    Returns:
        True if the proxy is a SOCKS proxy (socks4://, socks5://, socks5h://)
    """
    proxy_lower = proxy.lower()
    return proxy_lower.startswith("socks4://") or proxy_lower.startswith(
        "socks5://"
    ) or proxy_lower.startswith("socks5h://")


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

    Raises:
        ImportError: If SOCKS proxy is used but socksio is not installed
    """
    if not proxy:
        return None

    logger.info(f"[{provider_label}] 使用代理: {proxy}")

    # Check for SOCKS proxy and provide helpful error if socksio is not installed
    if _is_socks_proxy(proxy):
        try:
            import socksio  # noqa: F401
        except ImportError:
            raise ImportError(
                f"使用 SOCKS 代理需要安装 socksio 包。请运行以下命令安装：\n"
                f"  pip install 'httpx[socks]'\n"
                f"或者：\n"
                f"  pip install socksio\n"
                f"代理地址: {proxy}"
            ) from None

    return httpx.AsyncClient(proxy=proxy)
