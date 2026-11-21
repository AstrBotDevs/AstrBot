from __future__ import annotations

import dataclasses
from typing import Any

from astrbot_sdk.errors import InvalidRequest, NotFound

# Event methods legacy plugins may invoke through the bridge. Each maps to a
# method on the in-flight Host-side AstrMessageEvent; anything else is
# rejected so this never becomes a generic remote attribute channel.
_FORWARDED_METHODS = frozenset(
    {"send_typing", "stop_typing", "react", "get_group"},
)


class EventStateService:
    """Mirror event-level state and actions onto in-flight Host events.

    Isolated legacy plugins mutate or query the event they are handling
    (``call_llm`` suppression, typing indicators, reactions, group info).
    The bridge keeps the real Host events in ``_inflight_events`` keyed by
    unified message origin; this service applies the requested change there
    so the pipeline observes the same behavior as in-process plugins.
    """

    capability_id = "event.state"

    def __init__(self, inflight: dict[str, list[Any]]) -> None:
        """Initialize the service.

        Args:
            inflight: Live reference to the bridge's in-flight event map,
                keyed by unified message origin string.
        """
        self._inflight = inflight

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Serve event.state operations."""
        umo = payload.get("umo")
        if not isinstance(umo, str) or not umo:
            raise InvalidRequest("event.state operations require a umo string")
        events = self._inflight.get(umo) or []

        if operation == "set_call_llm":
            for event in events:
                event.call_llm = bool(payload.get("value"))
            return {}

        if operation == "call_method":
            method = payload.get("method")
            if method not in _FORWARDED_METHODS:
                raise NotFound(f"event.state does not forward method: {method}")
            args = payload.get("args")
            if args is not None and not isinstance(args, dict):
                raise InvalidRequest("event.state call_method args must be a dict")
            if not events:
                raise NotFound(f"no in-flight event for umo: {umo}")
            result = await getattr(events[-1], method)(**(args or {}))
            if result is not None and not dataclasses.is_dataclass(result):
                raise InvalidRequest(
                    f"event method {method} returned an unsupported result: "
                    f"{type(result)!r}",
                )
            return {
                "result": dataclasses.asdict(result) if result is not None else None,
            }

        raise NotFound(f"unknown event.state operation: {operation}")
