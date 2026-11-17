from collections.abc import Callable
from typing import Any

from astrbot.core.astr_agent_runtime.permission_mode import PERMISSION_MODES

WEBCHAT_REQUEST_FLAG_DEFAULTS = {
    "enable_inline_genui": True,
    "enable_default_system_prompt": True,
    "enable_streaming": True,
    "enable_reasoning": True,
}

# Per-conversation ChatUI options: the dashboard stores them per conversation
# and sends them with every request (send, regenerate, thread, WebSocket). The
# WebChat adapter puts each one on the event as an extra of the same name.
# To add an option, add its validator here and its field to ``ChatOptions`` in
# ``astrbot/dashboard/schemas.py`` (and the OpenAPI spec).
WEBCHAT_CHAT_OPTIONS: dict[str, Callable[[Any], bool]] = {
    # Permission mode; see astrbot/core/astr_agent_runtime/permission_mode.py.
    "permission_mode": lambda value: value in PERMISSION_MODES,
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


def resolve_webchat_chat_options(payload: dict[str, Any]) -> dict[str, Any]:
    """Resolve the per-conversation ChatUI options carried by a request.

    Args:
        payload: Incoming WebChat request or queue payload.

    Returns:
        Every supported option; missing or invalid values are None, so the
        configured behavior applies.
    """
    return {
        key: value if is_valid(value := payload.get(key)) else None
        for key, is_valid in WEBCHAT_CHAT_OPTIONS.items()
    }
