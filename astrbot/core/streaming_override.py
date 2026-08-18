"""Session-level streaming override resolution."""

from __future__ import annotations

from typing import Any

STREAMING_OVERRIDE_KEY = "streaming_response_override"
RESOLVED_STREAMING_EXTRA = "_resolved_streaming_response"


async def resolve_streaming_response(
    event: Any,
    config: dict[str, Any] | None,
    preferences: Any | None = None,
) -> bool:
    """Resolve and pin streaming mode for one in-flight request.

    Priority: ``event.extra['enable_streaming']`` > session override > global
    ``provider_settings.streaming_response``. The first resolution is stored
    on the event so a later ``/flow`` change cannot alter a running agent.

    Args:
        event: Current message event.
        config: Effective AstrBot config for this UMO.
        preferences: Shared preference store.

    Returns:
        Whether this request should stream.
    """

    pinned = event.get_extra(RESOLVED_STREAMING_EXTRA)
    if pinned is not None:
        return bool(pinned)

    extra = event.get_extra("enable_streaming")
    if extra is not None:
        value = bool(extra)
    else:
        override = None
        if preferences is not None:
            override = await preferences.session_get(
                event.unified_msg_origin,
                STREAMING_OVERRIDE_KEY,
                None,
            )
        if override is not None:
            value = bool(override)
        else:
            settings = (config or {}).get("provider_settings", {})
            value = bool(settings.get("streaming_response", False))

    event.set_extra(RESOLVED_STREAMING_EXTRA, value)
    return value
