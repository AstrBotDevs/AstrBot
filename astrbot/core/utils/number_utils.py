import math


def safe_positive_float(value: object, default: float) -> float:
    if not isinstance(value, (int, float, str)):
        return default

    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default

    if not math.isfinite(parsed) or parsed <= 0:
        return default
    return parsed
