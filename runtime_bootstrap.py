import ssl
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import aiohttp.connector as aiohttp_connector
import certifi


@dataclass
class BootstrapRecord:
    level: str
    message: str


_BOOTSTRAP_RECORDS: list[BootstrapRecord] = []


def _record(level: str, message: str) -> None:
    _BOOTSTRAP_RECORDS.append(BootstrapRecord(level=level, message=message))


def flush_bootstrap_records(log_obj: Any) -> None:
    if not _BOOTSTRAP_RECORDS:
        return

    level_methods: dict[str, Callable[[str], Any]] = {
        "info": getattr(log_obj, "info", None),
        "warning": getattr(log_obj, "warning", None),
        "error": getattr(log_obj, "error", None),
    }
    fallback = getattr(log_obj, "info", None)

    for record in _BOOTSTRAP_RECORDS:
        logger_method = level_methods.get(record.level, fallback)
        if callable(logger_method):
            logger_method(record.message)

    _BOOTSTRAP_RECORDS.clear()


def configure_runtime_ca_bundle() -> None:
    try:
        _record("info", "Bootstrapping runtime CA bundle.")
        ssl_context = ssl.create_default_context()
        ssl_context.load_verify_locations(cafile=certifi.where())

        if hasattr(aiohttp_connector, "_SSL_CONTEXT_VERIFIED"):
            aiohttp_connector._SSL_CONTEXT_VERIFIED = ssl_context
            _record(
                "info",
                "Configured aiohttp verified SSL context with system+certifi trust chain.",
            )
        else:
            _record(
                "warning",
                "aiohttp connector does not expose _SSL_CONTEXT_VERIFIED; skipped patch.",
            )
    except Exception as exc:
        _record(
            "error",
            f"Failed to configure runtime CA bundle for aiohttp: {exc!r}",
        )
        return


configure_runtime_ca_bundle()
