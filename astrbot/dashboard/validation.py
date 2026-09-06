"""Validation primitives for untrusted dashboard JSON objects."""

from collections.abc import Mapping
from typing import TypeGuard


def is_json_object(value: object) -> TypeGuard[dict[str, object]]:
    """Narrow a JSON object without assuming anything about its field values."""
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def object_path(data: Mapping[str, object], *keys: str) -> dict[str, object]:
    """Traverse object fields, rejecting missing or non-object values."""
    value: object = data
    for key in keys:
        if not is_json_object(value):
            raise ValueError(f"Invalid {key}: expected an object")
        value = value.get(key)
    if not is_json_object(value):
        raise ValueError(f"Invalid {'.'.join(keys)}: expected an object")
    return value


def is_string_list(value: object) -> TypeGuard[list[str]]:
    """Check every element before passing a list to a typed service."""
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def string_field(
    data: Mapping[str, object],
    key: str,
    default: str | None = None,
    *,
    error_type: type[Exception] = ValueError,
) -> str | None:
    """Read an optional string while rejecting structured or numeric values."""
    value = data.get(key, default)
    if value is not None and not isinstance(value, str):
        raise error_type(f"Invalid {key}: expected a string")
    return value


def string_list_field(
    data: Mapping[str, object],
    key: str,
    *,
    error_type: type[Exception] = ValueError,
) -> list[str] | None:
    """Read an optional list of strings, checking each element."""
    value = data.get(key)
    if value is None:
        return None
    if not is_string_list(value):
        raise error_type(f"Invalid {key}: expected a list of strings")
    return value


def integer_field(
    data: Mapping[str, object],
    key: str,
    default: int,
    *,
    error_type: type[Exception] = ValueError,
) -> int:
    """Read an integer option without coercing untrusted structures."""
    value = data.get(key, default)
    if not isinstance(value, int):
        raise error_type(f"Invalid {key}: expected an integer")
    return value
