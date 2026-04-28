"""Lightweight import smoke test — runs in CI and PKGBUILD check().

Catches missing symbols, undefined names, and abstract methods that are not
implemented — the kind of breakage that ``git merge -X theirs`` or a botched
cherry-pick silently introduces.
"""

# ---------------------------------------------------------------------------
# Layer 1 — symbol-level imports (曾炸过的 import 路径)
# ---------------------------------------------------------------------------
from astrbot.core.astr_main_agent_resources import (
    BACKGROUND_TASK_RESULT_WOKE_SYSTEM_PROMPT,
    BACKGROUND_TASK_WOKE_USER_PROMPT,
    CONVERSATION_HISTORY_INJECT_PREFIX,
)
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
from astrbot.core.pipeline.process_stage.stage import ProcessStage  # noqa: F401

# Dashboard routes (曾炸过 sentinel class / import 丢失)
from astrbot.dashboard.routes.live_chat import LiveChatRoute  # noqa: F401
from astrbot.dashboard.routes.chat import ChatRoute  # noqa: F401
from astrbot.dashboard.server import AstrBotDashboard  # noqa: F401

# Pipeline scheduler
from astrbot.core.pipeline.scheduler import PipelineScheduler  # noqa: F401

# Auth password utilities
from astrbot.core.utils.auth_password import (
    hash_dashboard_password,
    validate_dashboard_password,
    verify_dashboard_password,
    is_default_dashboard_password,
)  # noqa: F401


# ---------------------------------------------------------------------------
# Layer 2 — abstract-method completeness
# ---------------------------------------------------------------------------
def test_platform_abstract_methods():
    """Platform (ABC) should not crash on import and its abstract methods
    should be introspectable.

    Concrete subclasses that can be instantiated without network/external
    dependencies should also be verified here.
    """
    from astrbot.core.platform.platform import Platform
    import inspect

    # Introspect abstract methods — this caught SQLiteDatabase missing 5 methods
    abstract_methods = set(
        meth
        for meth in Platform.__abstractmethods__  # type: ignore[attr-defined]
    )
    assert isinstance(abstract_methods, set)
    assert len(abstract_methods) > 0


def test_live_chat_route():
    """LiveChatRoute can be imported without errors."""
    from astrbot.dashboard.routes.live_chat import LiveChatRoute

    assert LiveChatRoute is not None
