"""Network error handling utilities for providers."""

import ssl
from typing import Any

import httpx
import httpx2

from astrbot import logger
from astrbot.utils.http_ssl_common import build_ssl_context_with_certifi

_SYSTEM_SSL_CTX = build_ssl_context_with_certifi()


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
            httpx2.ConnectError,
            httpx2.ConnectTimeout,
            httpx2.ReadTimeout,
            httpx2.WriteTimeout,
            httpx2.PoolTimeout,
            httpx2.NetworkError,
            httpx2.ProxyError,
            httpx2.RequestError,
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


def create_proxy_client(
    provider_label: str,
    provider_config: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    verify: ssl.SSLContext | str | bool | None = None,
    httpx_module: Any = httpx,
    *,
    route: Any | None = None,
    destination_host: str | None = None,
) -> Any:
    """Create an httpx AsyncClient from an explicit ProxyRoute.

    Args:
        provider_label: The provider name for log prefix (e.g., "OpenAI", "Gemini")
        provider_config: Provider config containing ``proxy_mode`` and ``proxy_url``.
        headers: Optional custom headers to include in every request
        verify: Optional override for TLS verification.
        httpx_module: Optional httpx module to construct AsyncClient from.
        route: Pre-resolved route. When omitted, it is resolved from config.
        destination_host: Optional host used for ``no_proxy`` matching.

    Returns:
        An async client with ``trust_env=False`` and the resolved proxy.
    """
    from astrbot.core.utils.proxy_route import (
        create_routed_client,
        destination_host_from_url,
        resolve_proxy_route,
    )

    resolved_route = route or resolve_proxy_route(
        local_config=provider_config or {},
        destination_host=destination_host
        or destination_host_from_url((provider_config or {}).get("api_base")),
    )
    return create_routed_client(
        provider_label,
        resolved_route,
        headers=headers,
        verify=verify,
        httpx_module=httpx_module,
    )
