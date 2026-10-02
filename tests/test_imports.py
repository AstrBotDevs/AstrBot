"""Lightweight import smoke test.

Matches the checks in ``PKGBUILD check()`` plus extra guards for imports
that have broken in past merges. Imports stay at module scope to preserve
their collection-time initialization and registration behavior.
"""

from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
from astrbot.core.astr_main_agent_resources import (
    BACKGROUND_TASK_RESULT_WOKE_SYSTEM_PROMPT,
    BACKGROUND_TASK_WOKE_USER_PROMPT,
    CONVERSATION_HISTORY_INJECT_PREFIX,
)
from astrbot.core.pipeline.process_stage import stage as process_stage
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.utils.auth_password import (
    hash_dashboard_password,
    is_default_dashboard_password,
    validate_dashboard_password,
    verify_dashboard_password,
)
from astrbot.dashboard.api.chat import router as chat_router
from astrbot.dashboard.api.live_chat import router as live_chat_router
from astrbot.dashboard.server import AstrBotDashboard


def test_pkgbuild_imports() -> None:
    """The packaging smoke check's required exports remain available."""
    for prompt in (
        BACKGROUND_TASK_RESULT_WOKE_SYSTEM_PROMPT,
        BACKGROUND_TASK_WOKE_USER_PROMPT,
        CONVERSATION_HISTORY_INJECT_PREFIX,
    ):
        assert isinstance(prompt, str)
        assert prompt
    assert callable(AstrBotDashboard)
    assert callable(process_stage.ProcessStage)


def test_extra_import_guards() -> None:
    """Previously broken agent, scheduler, and chat imports remain available."""
    assert callable(FunctionToolExecutor)
    assert callable(PipelineScheduler)
    assert chat_router is not None


def test_password_utils_imports() -> None:
    """Password helpers imported by the smoke check remain callable."""
    for helper in (
        hash_dashboard_password,
        validate_dashboard_password,
        verify_dashboard_password,
        is_default_dashboard_password,
    ):
        assert callable(helper)


def test_platform_abstract_methods() -> None:
    """Platform (ABC) has abstract methods (catches missing implementations)."""
    from astrbot.core.platform.platform import Platform

    assert len(Platform.__dict__.get("__abstractmethods__", frozenset())) > 0


def test_live_chat_router() -> None:
    """The FastAPI live-chat router can be imported without errors."""
    from astrbot.dashboard.api.live_chat import router

    assert router is not None
    assert live_chat_router is router
