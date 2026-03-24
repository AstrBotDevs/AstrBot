from types import SimpleNamespace

import mcp
import pytest

from astrbot.core.agent.agent import Agent
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor


@pytest.mark.parametrize(
    ("value", "expected_bool", "expect_error"),
    [
        (True, True, False),
        ("true", True, False),
        ("1", True, False),
        ("yes", True, False),
        ("on", True, False),
        (" TRUE ", True, False),
        (False, False, False),
        ("false", False, False),
        ("0", False, False),
        ("no", False, False),
        ("off", False, False),
        ("", False, False),
        (" FALSE ", False, False),
        (None, False, False),
        ("not-a-bool", False, True),
        ("y", False, True),
        ("t", False, True),
        (123, False, True),
        ({}, False, True),
    ],
)
def test_parse_background_task_arg(value, expected_bool, expect_error):
    is_bg, error = FunctionToolExecutor._parse_background_task_arg(
        "transfer_to_subagent",
        value,
    )

    assert is_bg is expected_bool
    if expect_error:
        assert error is not None
        assert isinstance(error, mcp.types.CallToolResult)
        text_content = error.content[0]
        assert isinstance(text_content, mcp.types.TextContent)
        assert "invalid_background_task" in text_content.text
    else:
        assert error is None


@pytest.mark.asyncio
async def test_execute_invalid_background_task_early_error(monkeypatch):
    call_count = {"handoff": 0, "handoff_bg": 0}

    async def _fake_execute_handoff(cls, tool, run_context, **tool_args):
        call_count["handoff"] += 1
        yield mcp.types.CallToolResult(
            content=[mcp.types.TextContent(type="text", text="unexpected")]
        )

    async def _fake_execute_handoff_bg(cls, tool, run_context, **tool_args):
        call_count["handoff_bg"] += 1
        yield mcp.types.CallToolResult(
            content=[mcp.types.TextContent(type="text", text="unexpected")]
        )

    monkeypatch.setattr(
        FunctionToolExecutor,
        "_execute_handoff",
        classmethod(_fake_execute_handoff),
    )
    monkeypatch.setattr(
        FunctionToolExecutor,
        "_execute_handoff_background",
        classmethod(_fake_execute_handoff_bg),
    )

    tool = HandoffTool(agent=Agent(name="subagent"))
    event = SimpleNamespace(
        unified_msg_origin="webchat:FriendMessage:webchat!user!session",
        message_obj=SimpleNamespace(message=[]),
    )
    run_context = ContextWrapper(
        context=SimpleNamespace(event=event, context=SimpleNamespace())
    )

    results = []
    async for result in FunctionToolExecutor.execute(
        tool,
        run_context,
        input="hello",
        background_task="not-a-bool",
    ):
        results.append(result)

    assert len(results) == 1
    assert isinstance(results[0], mcp.types.CallToolResult)
    text_content = results[0].content[0]
    assert isinstance(text_content, mcp.types.TextContent)
    assert "invalid_background_task" in text_content.text
    assert call_count["handoff"] == 0
    assert call_count["handoff_bg"] == 0
