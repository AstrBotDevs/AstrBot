"""Normalize plain and model-backed Shipyard SDK responses."""

from typing import Any


def maybe_model_dump(value: object, *, copy_mapping: bool = False) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value) if copy_mapping else value
    dumped = dump_mapping_method(value, "model_dump")
    return dumped if dumped is not None else {}


def dump_mapping_method(value: object, method_name: str) -> dict[str, Any] | None:
    """Call an available serializer without mistaking an empty map for failure."""
    method = getattr(value, method_name, None)
    if callable(method):
        dumped = method()
        if isinstance(dumped, dict):
            return dumped
    return None
