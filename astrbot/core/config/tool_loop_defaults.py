"""Shared defaults and normalization helpers for local tool-loop controls."""

import logging
import typing as T

logger = logging.getLogger("Core")

DEFAULT_DEDUPLICATE_REPEATED_TOOL_RESULTS = True
DEFAULT_TOOL_RESULT_DEDUP_MAX_ENTRIES = 1024
DEFAULT_TOOL_ERROR_REPEAT_GUARD_THRESHOLD = 8


def normalize_positive_int_or_none(
    raw_value: T.Any,
    *,
    default: int,
    setting_name: str,
) -> int | None:
    """Normalize integer settings where <=0 means disabled (None)."""
    if isinstance(raw_value, bool):
        logger.warning(
            "Invalid %s=%s, fallback to %s.",
            setting_name,
            raw_value,
            default,
        )
        raw_value = default
    try:
        value = None if raw_value is None else int(raw_value)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid %s=%s, fallback to %s.",
            setting_name,
            raw_value,
            default,
        )
        value = default
    if value is not None and value <= 0:
        return None
    return value
