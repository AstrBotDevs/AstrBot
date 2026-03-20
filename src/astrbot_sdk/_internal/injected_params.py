from __future__ import annotations

import inspect
from typing import Any

try:
    from typing import get_type_hints
except ImportError:  # pragma: no cover
    get_type_hints = None

from .typing_utils import unwrap_optional

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


def legacy_arg_parameter_names(handler: Any) -> list[str]:
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):
        return []
    try:
        if get_type_hints is None:
            type_hints = {}
        else:
            type_hints = get_type_hints(handler)
    except Exception:
        type_hints = {}

    names: list[str] = []
    for parameter in signature.parameters.values():
        if parameter.kind not in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            continue
        if is_framework_injected_parameter(
            parameter.name, type_hints.get(parameter.name)
        ):
            continue
        names.append(parameter.name)
    return names


def _framework_injected_types() -> tuple[type[Any], ...]:
    from ..clients.llm import LLMResponse
    from ..context import Context
    from ..conversation import ConversationSession
    from ..events import MessageEvent
    from ..llm.entities import ProviderRequest
    from ..message.result import MessageEventResult
    from ..schedule import ScheduleContext

    return (
        Context,
        MessageEvent,
        ScheduleContext,
        ConversationSession,
        ProviderRequest,
        LLMResponse,
        MessageEventResult,
    )


__all__ = ["is_framework_injected_parameter", "legacy_arg_parameter_names"]
