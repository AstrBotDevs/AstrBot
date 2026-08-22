import math

from astrbot.core import logger


def coerce_int_config(
    value: object,
    *,
    default: int,
    min_value: int | None = None,
    field_name: str | None = None,
    source: str = "config",
    warn: bool = True,
) -> int:
    label = f"'{field_name}'" if field_name else "value"

    if isinstance(value, bool):
        if warn:
            logger.warning(
                "%s %s should be numeric, got boolean. Fallback to %s.",
                source,
                label,
                default,
            )
        parsed = default
    elif isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError:
            if warn:
                logger.warning(
                    "%s %s value '%s' is not numeric. Fallback to %s.",
                    source,
                    label,
                    value,
                    default,
                )
            parsed = default
    else:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            if warn:
                logger.warning(
                    "%s %s has unsupported type %s. Fallback to %s.",
                    source,
                    label,
                    type(value).__name__,
                    default,
                )
            parsed = default

    if min_value is not None and parsed < min_value:
        if warn:
            logger.warning(
                "%s %s=%s is below minimum %s. Fallback to %s.",
                source,
                label,
                parsed,
                min_value,
                min_value,
            )
        parsed = min_value
    return parsed


def coerce_float_config(
    value: object,
    *,
    default: float,
    min_value: float | None = None,
    max_value: float | None = None,
    field_name: str | None = None,
    source: str = "config",
    warn: bool = True,
) -> float:
    label = f"'{field_name}'" if field_name else "value"

    if value is None:
        parsed = default
        invalid_reason = None
    elif isinstance(value, bool):
        parsed = default
        invalid_reason = "got boolean"
    else:
        try:
            parsed = float(value)
            invalid_reason = None
            if not math.isfinite(parsed):
                parsed = default
                invalid_reason = f"has non-finite value {value!r}"
        except (TypeError, ValueError):
            parsed = default
            invalid_reason = f"has unsupported value {value!r}"

    if invalid_reason and warn:
        logger.warning(
            "%s %s %s. Fallback to %s.",
            source,
            label,
            invalid_reason,
            default,
        )

    if min_value is not None and parsed < min_value:
        if warn:
            logger.warning(
                "%s %s=%s is below minimum %s. Fallback to %s.",
                source,
                label,
                parsed,
                min_value,
                min_value,
            )
        parsed = min_value
    if max_value is not None and parsed > max_value:
        if warn:
            logger.warning(
                "%s %s=%s is above maximum %s. Fallback to %s.",
                source,
                label,
                parsed,
                max_value,
                max_value,
            )
        parsed = max_value
    return parsed
