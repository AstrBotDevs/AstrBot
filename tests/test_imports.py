"""Lightweight import smoke test.

Matches the checks in ``PKGBUILD check()`` plus extra guards for imports
that have broken in past merges.
"""

# ---------------------------------------------------------------------------
# PKGBUILD check() — mirrors ``python -c "from ... import ..."`` verbatim
# ---------------------------------------------------------------------------
from astrbot.core.astr_main_agent_resources import (
    BACKGROUND_TASK_RESULT_WOKE_SYSTEM_PROMPT,   # noqa: F401
    BACKGROUND_TASK_WOKE_USER_PROMPT,             # noqa: F401
    CONVERSATION_HISTORY_INJECT_PREFIX,           # noqa: F401
)
from astrbot.dashboard.server import AstrBotDashboard  # noqa: F401
import astrbot.core.pipeline.process_stage.stage  # noqa: F401


# ---------------------------------------------------------------------------
# Extra guards —曾炸过的 import 路径
# ---------------------------------------------------------------------------
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor  # noqa: F401
from astrbot.dashboard.routes.live_chat import LiveChatRoute  # noqa: F401
from astrbot.dashboard.routes.chat import ChatRoute  # noqa: F401
from astrbot.core.pipeline.scheduler import PipelineScheduler  # noqa: F401
from astrbot.core.utils.auth_password import (
    hash_dashboard_password,        # noqa: F401
    validate_dashboard_password,     # noqa: F401
    verify_dashboard_password,       # noqa: F401
    is_default_dashboard_password,   # noqa: F401
)


# ---------------------------------------------------------------------------
# Abstract-method completeness
# ---------------------------------------------------------------------------
def test_platform_abstract_methods():
    """Platform (ABC) has abstract methods (catches missing implementations)."""
    from astrbot.core.platform.platform import Platform

    assert len(Platform.__dict__.get('__abstractmethods__', frozenset())) > 0


def test_live_chat_route():
    """LiveChatRoute can be imported without errors."""
    from astrbot.dashboard.routes.live_chat import LiveChatRoute

    assert LiveChatRoute is not None
