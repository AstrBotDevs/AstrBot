"""Shared parsing for platform application registration responses."""

from collections.abc import Mapping


def registration_int_field(data: Mapping[str, object], key: str, default: int) -> int:
    """Accept numeric service values without coercing arbitrary strings."""
    value = data.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default
