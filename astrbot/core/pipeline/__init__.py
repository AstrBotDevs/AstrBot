"""Pipeline package exports.

This module intentionally avoids eager imports of all pipeline stage modules to
prevent import-time cycles. Stage classes remain available via lazy attribute
resolution for backward compatibility.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from astrbot.core.message.message_event_result import (
    EventResultType,
    MessageEventResult,
)

from .stage_order import STAGES_ORDER

_LAZY_EXPORTS = {
    "ContentSafetyCheckStage": (
        "astrbot.core.pipeline.content_safety_check.stage",
        "ContentSafetyCheckStage",
    ),
    "PreProcessStage": (
        "astrbot.core.pipeline.preprocess_stage.stage",
        "PreProcessStage",
    ),
    "ProcessStage": (
        "astrbot.core.pipeline.process_stage.stage",
        "ProcessStage",
    ),
    "RateLimitStage": (
        "astrbot.core.pipeline.rate_limit_check.stage",
        "RateLimitStage",
    ),
    "RespondStage": (
        "astrbot.core.pipeline.respond.stage",
        "RespondStage",
    ),
    "ResultDecorateStage": (
        "astrbot.core.pipeline.result_decorate.stage",
        "ResultDecorateStage",
    ),
    "SessionStatusCheckStage": (
        "astrbot.core.pipeline.session_status_check.stage",
        "SessionStatusCheckStage",
    ),
    "WakingCheckStage": (
        "astrbot.core.pipeline.waking_check.stage",
        "WakingCheckStage",
    ),
    "WhitelistCheckStage": (
        "astrbot.core.pipeline.whitelist_check.stage",
        "WhitelistCheckStage",
    ),
}

__all__ = [
    "ContentSafetyCheckStage",
    "EventResultType",
    "MessageEventResult",
    "PreProcessStage",
    "ProcessStage",
    "RateLimitStage",
    "RespondStage",
    "ResultDecorateStage",
    "SessionStatusCheckStage",
    "STAGES_ORDER",
    "WakingCheckStage",
    "WhitelistCheckStage",
]


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_path, attr_name = _LAZY_EXPORTS[name]
    module = import_module(module_path)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
