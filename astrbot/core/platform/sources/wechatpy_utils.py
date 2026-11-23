"""Normalize textual fields at the WeChat SDK descriptor boundary."""

from collections.abc import Mapping


def message_text(message: object, attribute: str, raw_key: str) -> str:
    """Decode incoming bytes even when an SDK descriptor decodes them eagerly."""
    try:
        value = getattr(message, attribute)
    except UnicodeDecodeError:
        raw = getattr(message, "_data", None)
        if not isinstance(raw, Mapping) or not isinstance(raw.get(raw_key), bytes):
            raise
        value = raw[raw_key]
    return (
        value.decode("utf-8", errors="replace")
        if isinstance(value, bytes)
        else str(value)
    )
