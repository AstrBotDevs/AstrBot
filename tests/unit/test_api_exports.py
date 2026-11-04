"""Compatibility contracts for the documented plugin SDK import paths."""

import importlib
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("public_module", "core_module", "names"),
    [
        (
            "astrbot.api",
            "astrbot.core.agent.tool",
            ("FunctionTool", "ToolExecResult", "ToolSet"),
        ),
        (
            "astrbot.api.agents",
            "astrbot.core.agent.tool",
            ("FunctionTool", "ToolExecResult", "ToolSet"),
        ),
        (
            "astrbot.api.agents",
            "astrbot.core.agent.tool_executor",
            ("BaseFunctionToolExecutor",),
        ),
        (
            "astrbot.api.agents",
            "astrbot.core.db.po",
            ("Conversation",),
        ),
        (
            "astrbot.api.agents",
            "astrbot.core.agent.message",
            ("AssistantMessageSegment", "TextPart", "UserMessageSegment"),
        ),
        (
            "astrbot.api.agents",
            "astrbot.core.agent.run_context",
            ("ContextWrapper",),
        ),
        (
            "astrbot.api.agents",
            "astrbot.core.astr_agent_context",
            ("AgentContextWrapper", "AstrAgentContext"),
        ),
        ("astrbot.api.provider", "astrbot.core.db.po", ("Conversation",)),
        (
            "astrbot.api.util",
            "astrbot.core.utils.session_waiter",
            ("SessionController", "SessionFilter", "SessionWaiter", "session_waiter"),
        ),
        (
            "astrbot.api.util",
            "astrbot.core.utils.astrbot_path",
            ("get_astrbot_data_path", "get_astrbot_plugin_data_path"),
        ),
        (
            "astrbot.api.platform",
            "astrbot.core.platform.message_session",
            ("MessageSession",),
        ),
    ],
)
def test_sdk_exports_preserve_existing_type_and_function_identity(
    public_module, core_module, names
):
    """Keep SDK and Core callers interoperable through the same objects.

    Args:
        public_module: Documented plugin SDK module.
        core_module: Existing implementation or compatibility module.
        names: Public types and functions shared by both import paths.
    """
    public = importlib.import_module(public_module)
    core = importlib.import_module(core_module)
    for name in names:
        assert name in public.__all__
        assert getattr(public, name) is getattr(core, name)


@pytest.mark.parametrize(
    "first_import",
    [
        "astrbot.api.agents",
        "astrbot.core.star.context",
        "astrbot.core.config.default",
    ],
)
def test_sdk_import_order_preserves_agent_decorator_and_platform_independence(
    first_import,
):
    """Check fresh imports without relying on modules cached by other tests.

    Args:
        first_import: Entry point imported before the rest of the SDK.
    """
    script = """
import importlib
import sys

importlib.import_module(sys.argv[1])
import astrbot.api as api
import astrbot.api.agents
import astrbot.api.platform
import astrbot.api.provider
import astrbot.api.util
from astrbot.core.star.register import register_agent

assert api.agent is register_agent
assert callable(api.agent)
assert 'astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter' not in sys.modules
assert 'astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script, first_import],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
