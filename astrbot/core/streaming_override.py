"""Session-level streaming override resolution."""

from __future__ import annotations

from typing import Any

STREAMING_OVERRIDE_KEY = "streaming_response_override"
RESOLVED_STREAMING_EXTRA = "_resolved_streaming_response"


async def resolve_streaming_response(
    event: Any,
    config: dict[str, Any] | None,
    preferences: Any | None = None,
    *,
    default: bool | None = None,
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

    pinned = _event_extra(event, RESOLVED_STREAMING_EXTRA)
    if pinned is not None:
        return bool(pinned)

    extra = _event_extra(event, "enable_streaming")
    if extra is not None:
        value = bool(extra)
    else:
        override = None
        if preferences is not None:
            umo = getattr(event, "unified_msg_origin", "") or ""
            override = await preferences.session_get(
                umo,
                STREAMING_OVERRIDE_KEY,
                None,
            )
        if override is not None:
            value = bool(override)
        else:
            settings = (config or {}).get("provider_settings", {})
            if "streaming_response" in settings:
                value = bool(settings.get("streaming_response", False))
            elif default is not None:
                value = bool(default)
            else:
                value = False

    _event_set_extra(event, RESOLVED_STREAMING_EXTRA, value)
    return value


def _event_extra(event: Any, key: str, default: Any = None) -> Any:
    getter = getattr(event, "get_extra", None)
    if callable(getter):
        try:
            return getter(key, default)
        except TypeError:
            try:
                value = getter(key)
            except Exception:
                return default
            return default if value is None else value
        except Exception:
            return default
    extra = getattr(event, "_extra", None)
    if isinstance(extra, dict):
        return extra.get(key, default)
    return default


def _event_set_extra(event: Any, key: str, value: Any) -> None:
    setter = getattr(event, "set_extra", None)
    if callable(setter):
        setter(key, value)
        return
    extra = getattr(event, "_extra", None)
    if isinstance(extra, dict):
        extra[key] = value
        return
    try:
        event._extra = {key: value}
    except Exception:
        return
