from astrbot.core.lang import t
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
                t("msg-c5d2510a", source=source, label=label, default=default),
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
                    t("msg-6040637c", source=source, label=label, value=value, default=default),
                )
            parsed = default
    else:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            if warn:
                logger.warning(
                    t("msg-19aad160", source=source, label=label, res=type(value).__name__, default=default),
                )
            parsed = default

    if min_value is not None and parsed < min_value:
        if warn:
            logger.warning(
                t("msg-21ec4bb0", source=source, label=label, parsed=parsed, min_value=min_value),
            )
        parsed = min_value
    return parsed
