from typing import Any

WEBCHAT_REQUEST_FLAG_DEFAULTS = {
    "enable_inline_genui": True,
    "enable_default_system_prompt": True,
    "enable_streaming": True,
}


def resolve_webchat_request_flags(payload: dict[str, Any]) -> dict[str, bool]:
    """Resolve supported WebChat flags with legacy top-level fallbacks.

    A boolean value in ``flags`` has the highest priority, followed by the
    legacy top-level field, then the server default.

    Args:
        payload: Incoming WebChat request or queue payload.

    Returns:
        A complete mapping of supported WebChat flags.
    """
    raw_flags = payload.get("flags")
    flags = raw_flags if isinstance(raw_flags, dict) else {}
    resolved: dict[str, bool] = {}
    for key, default in WEBCHAT_REQUEST_FLAG_DEFAULTS.items():
        value = flags.get(key)
        if not isinstance(value, bool):
            value = payload.get(key)
        resolved[key] = value if isinstance(value, bool) else default
    return resolved
