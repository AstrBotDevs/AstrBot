import logging
import ssl
import threading

import aiohttp
import certifi

logger = logging.getLogger("astrbot")

_CERTIFI_WARNING_LOGGED = False
_SHARED_TLS_CONTEXT: ssl.SSLContext | None = None
_SHARED_TLS_CONTEXT_LOCK = threading.Lock()


def build_ssl_context_with_certifi() -> ssl.SSLContext:
    """Build an SSL context from system trust store and add certifi CAs."""
    global _CERTIFI_WARNING_LOGGED
    global _SHARED_TLS_CONTEXT

    if _SHARED_TLS_CONTEXT is not None:
        return _SHARED_TLS_CONTEXT

    with _SHARED_TLS_CONTEXT_LOCK:
        if _SHARED_TLS_CONTEXT is not None:
            return _SHARED_TLS_CONTEXT

        ssl_context = ssl.create_default_context()

        try:
            ssl_context.load_verify_locations(cafile=certifi.where())
        except Exception as exc:
            if not _CERTIFI_WARNING_LOGGED:
                logger.warning(
                    "Failed to load certifi CA bundle into SSL context; "
                    "falling back to system trust store only: %s",
                    exc,
                )
                _CERTIFI_WARNING_LOGGED = True

        _SHARED_TLS_CONTEXT = ssl_context
        return _SHARED_TLS_CONTEXT


def build_tls_connector() -> aiohttp.TCPConnector:
    return aiohttp.TCPConnector(ssl=build_ssl_context_with_certifi())
