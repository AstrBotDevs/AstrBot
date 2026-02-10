import logging
import ssl
import threading

import aiohttp

from http_ssl_common import build_ssl_context_with_certifi as _build_ssl_context

logger = logging.getLogger("astrbot")

_SHARED_TLS_CONTEXT: ssl.SSLContext | None = None
_SHARED_TLS_CONTEXT_LOCK = threading.Lock()


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


def build_tls_connector() -> aiohttp.TCPConnector:
    return aiohttp.TCPConnector(ssl=build_ssl_context_with_certifi())
