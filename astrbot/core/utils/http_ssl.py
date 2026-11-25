import logging
import os
import ssl
import threading

import aiohttp
import certifi

from astrbot.utils.http_ssl_common import (
    build_ssl_context_with_certifi as _build_ssl_context,
)

logger = logging.getLogger("astrbot")

_SHARED_TLS_CONTEXT: ssl.SSLContext | None = None
_SHARED_TLS_CONTEXT_LOCK = threading.Lock()
_CERTIFI_CONTEXTS: dict[bool, ssl.SSLContext] = {}


def build_ssl_context_with_certifi() -> ssl.SSLContext:
    """Build an SSL context from system trust store and add certifi CAs."""
    global _SHARED_TLS_CONTEXT

    if _SHARED_TLS_CONTEXT is not None:
        return _SHARED_TLS_CONTEXT

    with _SHARED_TLS_CONTEXT_LOCK:
        if _SHARED_TLS_CONTEXT is not None:
            return _SHARED_TLS_CONTEXT

        _SHARED_TLS_CONTEXT = _build_ssl_context(log_obj=logger)
        return _SHARED_TLS_CONTEXT


def get_certifi_ssl_context(*, for_httpx: bool) -> ssl.SSLContext:
    """Return a shared context that trusts only the certifi CA bundle.

    Args:
        for_httpx: Use a separate context for httpcore, which sets ALPN.

    Returns:
        The context for the selected transport.
    """
    context = _CERTIFI_CONTEXTS.get(for_httpx)
    if context is not None:
        return context
    with _SHARED_TLS_CONTEXT_LOCK:
        context = _CERTIFI_CONTEXTS.get(for_httpx)
        if context is None:
            context = ssl.create_default_context(cafile=certifi.where())
            _CERTIFI_CONTEXTS[for_httpx] = context
        return context


def get_httpx_default_verify() -> ssl.SSLContext | bool:
    """Reuse HTTPX's default CA bundle unless the environment overrides it.

    Returns:
        True to let HTTPX resolve the environment, or the shared certifi context.
    """
    if os.environ.get("SSL_CERT_FILE") or os.environ.get("SSL_CERT_DIR"):
        return True
    return get_certifi_ssl_context(for_httpx=True)


def build_tls_connector(*, certifi_only: bool = False) -> aiohttp.TCPConnector:
    """Create a connector with a shared, verified TLS context.

    Args:
        certifi_only: Use certifi without adding system roots.

    Returns:
        A connector owned by the calling session.
    """
    context = (
        get_certifi_ssl_context(for_httpx=False)
        if certifi_only
        else build_ssl_context_with_certifi()
    )
    return aiohttp.TCPConnector(ssl=context)
