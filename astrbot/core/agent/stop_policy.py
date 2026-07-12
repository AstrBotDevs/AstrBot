from typing import Any

AGENT_OUTPUT_DELIVERY_CONFIRMED_KEY = "_agent_output_delivery_confirmed"


class AgentOutputStopped(Exception):
    """Unwind streaming adapters without triggering broad error handlers."""


def event_requests_agent_stop(event: Any) -> bool:
    """Return whether an event requests the current agent run to stop.

    Args:
        event: Event-like object that may expose stop state and extras.

    Returns:
        Whether hard stop, soft stop, or user-aborted state is active.
    """
    if event is None:
        return False

    is_stopped = getattr(event, "is_stopped", None)
    if callable(is_stopped) and is_stopped():
        return True

    get_extra = getattr(event, "get_extra", None)
    if not callable(get_extra):
        return False
    return bool(get_extra("agent_stop_requested")) or bool(
        get_extra("agent_user_aborted")
    )
