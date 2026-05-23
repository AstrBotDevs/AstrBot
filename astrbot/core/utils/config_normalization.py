from __future__ import annotations

from typing import Any


def to_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def to_int(value: Any, default: int, min_value: int | None = None) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    if min_value is not None:
        parsed = max(parsed, min_value)
    return parsed


def to_non_negative_int(value: Any, default: int = 0) -> int:
    return max(0, to_int(value, default))


def to_ratio(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = default
    if parsed > 1.0 and parsed <= 100.0:
        parsed = parsed / 100.0
    return min(max(parsed, 0.0), 1.0)
