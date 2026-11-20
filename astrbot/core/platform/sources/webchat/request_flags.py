from typing import Any

WEBCHAT_REQUEST_FLAG_DEFAULTS = {
    "enable_inline_genui": True,
    "enable_default_system_prompt": True,
    "enable_streaming": True,
    "enable_reasoning": True,
}

WEBCHAT_REASONING_EFFORTS = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)


def resolve_webchat_request_flags(payload: dict[str, Any]) -> dict[str, Any]:
    """Resolve supported WebChat flags with legacy top-level fallbacks.

    A boolean value in ``flags`` has the highest priority, followed by the
    legacy top-level field, then the server default.

    ``reasoning_effort`` is read only from ``flags``. A missing or invalid value
    resolves to ``None`` so the provider keeps the model's default level.

    Args:
        payload: Incoming WebChat request or queue payload.

    Returns:
        A complete mapping of supported WebChat flags.
    """
    raw_flags = payload.get("flags")
    flags = raw_flags if isinstance(raw_flags, dict) else {}
    resolved: dict[str, Any] = {}
    for key, default in WEBCHAT_REQUEST_FLAG_DEFAULTS.items():
        value = flags.get(key)
        if not isinstance(value, bool):
            value = payload.get(key)
        resolved[key] = value if isinstance(value, bool) else default
    effort = flags.get("reasoning_effort")
    if isinstance(effort, str):
        effort = effort.strip().lower()
    resolved["reasoning_effort"] = (
        effort if effort in WEBCHAT_REASONING_EFFORTS else None
    )
    return resolved
