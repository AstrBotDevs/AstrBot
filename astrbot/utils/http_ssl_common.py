import logging
import ssl
from typing import Any

import certifi

_LOGGER = logging.getLogger(__name__)


def build_ssl_context_with_certifi(log_obj: Any | None = None) -> ssl.SSLContext:
    logger = log_obj or _LOGGER

    ssl_context = ssl.create_default_context()
    try:
        ssl_context.load_verify_locations(cafile=certifi.where())
    except Exception as exc:
        if logger and hasattr(logger, "warning"):
            logger.warning(
                "Failed to load certifi CA bundle into SSL context; "
                "falling back to system trust store only: %s",
                exc,
            )

    return ssl_context
