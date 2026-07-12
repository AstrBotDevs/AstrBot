import math

from astrbot.core import DEMO_MODE

DEMO_MODE_ERROR_MESSAGE = "You are not permitted to do this operation in demo mode"


def is_demo_mode() -> bool:
    return DEMO_MODE


def is_sandbox_name_conflict(error: Exception) -> bool:
    return isinstance(error, RuntimeError) and str(error).startswith("Sandbox name ")


def is_sandbox_limit_error(error: Exception) -> bool:
    return isinstance(error, RuntimeError) and str(error).startswith(
        "Sandbox limit reached"
    )


def is_sandbox_user_error(error: Exception) -> bool:
    if not isinstance(error, (RuntimeError, ValueError)):
        return False
    message = str(error)
    return (
        is_sandbox_name_conflict(error)
        or is_sandbox_limit_error(error)
        or "does not support persistent sandboxes" in message
        or "retention_policy must be" in message
        or "sandbox_name must be" in message
    )


def sanitize_shell_timeout(value, default: float = 300) -> float:
    if isinstance(value, bool):
        return default
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(timeout) or timeout <= 0:
        return default
    return timeout
