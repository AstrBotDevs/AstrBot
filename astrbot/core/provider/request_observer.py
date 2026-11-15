"""Optional observation of provider attempts, independent of Agent persistence."""

import inspect
from collections.abc import Callable
from typing import Protocol


class RequestAttemptObserver(Protocol):
    """Observe network attempts without requiring a specific event implementation."""

    async def before_network_attempt(self) -> None:
        """Acknowledge an attempt before any network side effect."""
        ...

    async def finish(self, status: str, *, error_code: str | None = None) -> None:
        """Acknowledge the terminal state of a failed network attempt.

        Args:
            status: Attempt terminal status.
            error_code: Exception class or stable error code.
        """
        ...


def request_recorder_kwargs(
    call: Callable, recorder: RequestAttemptObserver | None
) -> dict:
    """Pass instrumentation only to adapters that explicitly accept it.

    Args:
        call: Provider method, which may be implemented by an older plugin.
        recorder: Optional request attempt recorder.

    Returns:
        Local instrumentation arguments, never arbitrary model request kwargs.
    """
    if (
        recorder is not None
        and "request_event_recorder" in inspect.signature(call).parameters
    ):
        return {"request_event_recorder": recorder}
    return {}
