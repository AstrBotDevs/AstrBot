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
