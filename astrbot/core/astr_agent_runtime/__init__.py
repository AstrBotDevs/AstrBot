"""The built-in AstrBot runtime and its native capabilities."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .runtime import AstrAgentRuntime as AstrAgentRuntime

__all__ = ["AstrAgentRuntime"]


def __getattr__(name: str) -> object:
    """Load the runtime only when requested, keeping capability imports lightweight.

    Args:
        name: Public package attribute requested by the caller.

    Returns:
        The native runtime class.

    Raises:
        AttributeError: If the requested attribute is not exported.
    """
    if name == "AstrAgentRuntime":
        from .runtime import AstrAgentRuntime

        return AstrAgentRuntime
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
