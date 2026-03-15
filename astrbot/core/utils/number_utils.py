import math


def safe_positive_float(value: object, default: float) -> float:
    """Parse a value to a positive float.

    Args:
        value: The value to parse (int, float, str, or other).
        default: Default value to return if parsing fails or value is not positive.

    Returns:
        The parsed positive float, or the default value.
        Note: 0 is considered a valid value to allow disabling via config (e.g., TTL=0 disables dedup).
    """
    if not isinstance(value, (int, float, str)):
        return default

    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default

    # Allow 0 to pass through (for disabling via config), but reject negative values
    if not math.isfinite(parsed) or parsed < 0:
        return default
    return parsed
