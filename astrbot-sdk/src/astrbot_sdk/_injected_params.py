from __future__ import annotations

from typing import Any

from ._typing_utils import unwrap_optional

_INJECTED_PARAMETER_NAMES = {
    "event",
    "ctx",
    "context",
    "sched",
    "schedule",
    "conversation",
    "conv",
}


def is_framework_injected_parameter(name: str, annotation: Any) -> bool:
    if name in _INJECTED_PARAMETER_NAMES:
        return True
    normalized, _is_optional = unwrap_optional(annotation)
    if normalized is None:
        return False
    try:
        injected_types = _framework_injected_types()
    except Exception:
        return False
    if normalized in injected_types:
        return True
    if isinstance(normalized, type):
        return issubclass(normalized, injected_types)
    return False


def _framework_injected_types() -> tuple[type[Any], ...]:
    from .clients.llm import LLMResponse
    from .context import Context
    from .conversation import ConversationSession
    from .events import MessageEvent
    from .llm.entities import ProviderRequest
    from .message_result import MessageEventResult
    from .schedule import ScheduleContext

    return (
        Context,
        MessageEvent,
        ScheduleContext,
        ConversationSession,
        ProviderRequest,
        LLMResponse,
        MessageEventResult,
    )


__all__ = ["is_framework_injected_parameter"]
