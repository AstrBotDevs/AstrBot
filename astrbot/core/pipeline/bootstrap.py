"""The immutable built-in pipeline stage order."""

from __future__ import annotations

from collections.abc import Sequence

from .stage import Stage


def builtin_stage_classes() -> Sequence[type[Stage]]:
    """Return the fixed, production pipeline stage classes in execution order.

    Imports are intentionally local: importing the pipeline package remains
    lightweight, while scheduler construction obtains a stable tuple rather
    than populating a process-global mutable registry.
    """
    from .content_safety_check.stage import ContentSafetyCheckStage
    from .group_message_history.stage import GroupMessageHistoryStage
    from .preprocess_stage.stage import PreProcessStage
    from .process_stage.stage import ProcessStage
    from .rate_limit_check.stage import RateLimitStage
    from .respond.stage import RespondStage
    from .result_decorate.stage import ResultDecorateStage
    from .session_status_check.stage import SessionStatusCheckStage
    from .waking_check.stage import WakingCheckStage
    from .whitelist_check.stage import WhitelistCheckStage

    return (
        WakingCheckStage,
        WhitelistCheckStage,
        SessionStatusCheckStage,
        RateLimitStage,
        ContentSafetyCheckStage,
        PreProcessStage,
        GroupMessageHistoryStage,
        ProcessStage,
        ResultDecorateStage,
        RespondStage,
    )


__all__ = ["builtin_stage_classes"]
