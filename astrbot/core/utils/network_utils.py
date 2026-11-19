"""Network error handling utilities for providers."""

import ssl
from typing import Any
from urllib.parse import urlsplit

import httpx

from astrbot import logger
from astrbot.core.utils.http_ssl import build_ssl_context_with_certifi

_UNSET: Any = object()


def _redact_proxy_url(proxy: str) -> str:
    """Mask userinfo credentials in a proxy URL before logging.

    Args:
        proxy: Raw proxy URL string.

    Returns:
        Proxy URL with username and password replaced by ``***`` when present.
    """
    try:
        parsed = urlsplit(proxy)
    except ValueError:
        return proxy
    if parsed.username is None and parsed.password is None:
        return proxy
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port_part = f":{parsed.port}" if parsed.port is not None else ""
    path_part = parsed.path or ""
    query_part = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme}://***@{host}{port_part}{path_part}{query_part}"


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
            f"[{provider_label}] Network or proxy connection failed ({error_type}). "
            f"Proxy: {effective_proxy}; error: {error}"
        )
    else:
        logger.error(
            f"[{provider_label}] Network connection failed ({error_type}): {error}"
        )


def create_proxy_client(
    provider_label: str,
    proxy: str | None = None,
    headers: dict[str, str] | None = None,
    verify: ssl.SSLContext | str | bool | None = None,
    httpx_module: Any = httpx,
    *,
    timeout: float | httpx.Timeout | None = _UNSET,
    trust_env: bool | None = None,
    follow_redirects: bool | None = None,
    base_url: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """Create an httpx AsyncClient reusing the shared hybrid SSL context.

    Uses a process-wide SSL context that combines the system SSL certificate
    store with certifi as a fallback, ensuring compatibility across
    environments while avoiding duplicating CA stores across provider clients.

    Note: The caller is responsible for closing the client when done.
    Consider using the client as a context manager or calling aclose() explicitly.

    Args:
        provider_label: The provider name for log prefix (e.g., "OpenAI", "Gemini").
        proxy: The proxy address (e.g., "http://127.0.0.1:7890"), or None/empty.
        headers: Optional custom headers to include in every request.
        verify: Optional override for TLS verification. Defaults to the shared
            hybrid SSL context (system store + certifi) when not provided.
        httpx_module: Optional httpx module to construct AsyncClient from. This is
            useful when a provider SDK performs isinstance checks against its own
            httpx import.
        timeout: Optional request timeout passed to AsyncClient (including explicit ``None``).
        trust_env: Optional trust_env override passed to AsyncClient.
        follow_redirects: Optional follow_redirects override passed to AsyncClient.
        base_url: Optional base URL passed to AsyncClient.
        transport: Optional custom transport passed to AsyncClient.

    Returns:
        An httpx.AsyncClient created with the shared hybrid SSL context; the
        proxy is applied only if one is provided.
    """
    resolved_verify = build_ssl_context_with_certifi() if verify is None else verify
    client_kwargs: dict[str, Any] = {
        "verify": resolved_verify,
        "headers": headers,
    }
    if timeout is not _UNSET:
        client_kwargs["timeout"] = timeout
    if trust_env is not None:
        client_kwargs["trust_env"] = trust_env
    if follow_redirects is not None:
        client_kwargs["follow_redirects"] = follow_redirects
    if base_url is not None:
        client_kwargs["base_url"] = base_url
    if transport is not None:
        client_kwargs["transport"] = transport
    if proxy:
        logger.info(f"[{provider_label}] Using proxy: {_redact_proxy_url(proxy)}")
        client_kwargs["proxy"] = proxy
    return httpx_module.AsyncClient(**client_kwargs)


def create_openai_http_client(
    provider_label: str,
    proxy: str | None = None,
) -> httpx.AsyncClient:
    """Create an httpx AsyncClient compatible with the installed openai SDK.

    Args:
        provider_label: The provider name for log prefix.
        proxy: Optional proxy URL string.

    Returns:
        An ``httpx.AsyncClient`` constructed from the OpenAI SDK's own
        ``httpx`` module when available, with redirect following enabled.
    """
    httpx_module: Any = httpx
    try:
        from openai import _base_client as openai_base_client

        httpx_module = getattr(openai_base_client, "httpx", httpx)
    except ImportError:
        pass
    return create_proxy_client(
        provider_label,
        proxy,
        httpx_module=httpx_module,
        follow_redirects=True,
    )
