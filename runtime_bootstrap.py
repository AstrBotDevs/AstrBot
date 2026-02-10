import ssl
from typing import Any

import aiohttp.connector as aiohttp_connector
import certifi

_BOOTSTRAP_RECORDS: list[tuple[str, str]] = []
_TLS_BOOTSTRAP_DONE = False


def _record(level: str, message: str) -> None:
    _BOOTSTRAP_RECORDS.append((level, message))


def flush_bootstrap_records(log_obj: Any) -> None:
    if not _BOOTSTRAP_RECORDS:
        return

    for level, message in _BOOTSTRAP_RECORDS:
        logger_method = getattr(log_obj, level, None) or getattr(log_obj, "info", None)
        if callable(logger_method):
            logger_method(message)

    _BOOTSTRAP_RECORDS.clear()


def _try_patch_aiohttp_ssl_context(ssl_context: ssl.SSLContext) -> bool:
    attr_name = "_SSL_CONTEXT_VERIFIED"

    if not hasattr(aiohttp_connector, attr_name):
        _record(
            "warning",
            "aiohttp connector does not expose _SSL_CONTEXT_VERIFIED; skipped patch.",
        )
        return False

    current_value = getattr(aiohttp_connector, attr_name, None)
    if current_value is not None and not isinstance(current_value, ssl.SSLContext):
        _record(
            "warning",
            "aiohttp connector exposes _SSL_CONTEXT_VERIFIED with unexpected type; skipped patch.",
        )
        return False

    setattr(aiohttp_connector, attr_name, ssl_context)
    _record(
        "info",
        "Configured aiohttp verified SSL context with system+certifi trust chain.",
    )
    return True


def configure_runtime_ca_bundle() -> bool:
    global _TLS_BOOTSTRAP_DONE

    if _TLS_BOOTSTRAP_DONE:
        return True

    try:
        _record("info", "Bootstrapping runtime CA bundle.")
        ssl_context = ssl.create_default_context()
        ssl_context.load_verify_locations(cafile=certifi.where())
        _TLS_BOOTSTRAP_DONE = _try_patch_aiohttp_ssl_context(ssl_context)
        return _TLS_BOOTSTRAP_DONE
    except Exception as exc:
        _record(
            "error",
            f"Failed to configure runtime CA bundle for aiohttp: {exc!r}",
        )
        return False


def initialize_runtime_bootstrap(log_obj: Any | None = None) -> bool:
    configured = configure_runtime_ca_bundle()
    if log_obj is not None:
        flush_bootstrap_records(log_obj)
    return configured


configure_runtime_ca_bundle()
