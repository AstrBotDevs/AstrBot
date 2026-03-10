from typing import Any

_TRUTHY_STRINGS = frozenset({"1", "true", "yes", "y", "on"})


def parse_bool(value: Any, default: bool = False) -> bool:
    """Parse bool-like config values with consistent string handling."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in _TRUTHY_STRINGS
    return bool(value)
