DEFAULT_REPEAT_REPLY_GUARD_THRESHOLD = 3


def normalize_repeat_reply_guard_threshold(value, *, invalid_fallback: int = 0) -> int:
    if isinstance(value, bool):
        return invalid_fallback
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return invalid_fallback
    return max(0, parsed)


def normalize_config_repeat_reply_guard_threshold(value) -> int:
    return normalize_repeat_reply_guard_threshold(
        value,
        invalid_fallback=DEFAULT_REPEAT_REPLY_GUARD_THRESHOLD,
    )
