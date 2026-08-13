"""Regression coverage for the unified function-tool authorization boundary."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import mcp
import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
from astrbot.core.tools.function_tool_manager import FunctionToolManager


def _tool(name: str = "plugin_tool") -> FunctionTool:
    return FunctionTool(
        name=name,
        description="test tool",
        parameters={"type": "object", "properties": {}},
        handler=AsyncMock(return_value="ok"),
    )


def _run_context(*, authorization=None, complete=True):
    event = SimpleNamespace(
        subject=SimpleNamespace(id="im:test:bot:user", authenticated=True),
        resource=SimpleNamespace(config_id="default"),
        auth_context=SimpleNamespace(),
    )
    if not complete:
        event.auth_context = None
    runtime = SimpleNamespace(authorization=authorization)
    return ContextWrapper(context=SimpleNamespace(event=event, context=runtime))


def test_get_full_tool_set_returns_original_tools():
    manager = FunctionToolManager()
    tool = _tool()
    manager.func_list = [tool]

    assert manager.get_full_tool_set().get_tool(tool.name) is tool


def test_unclaimed_plugin_tools_use_narrow_function_action():
    assert FunctionToolExecutor._required_actions(_tool()) == ("tool.function",)


@pytest.mark.asyncio
async def test_execution_denies_when_authorization_context_is_missing():
    tool = _tool()
    run_context = _run_context(authorization=None)

    results = [
        item
        async for item in FunctionToolExecutor.execute(tool, run_context)
    ]

    assert len(results) == 1
    assert isinstance(results[0], mcp.types.CallToolResult)
    assert "Permission denied" in results[0].content[0].text
    tool.handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_execution_checks_required_action_before_handler():
    authorization = SimpleNamespace(
        authorize=AsyncMock(return_value=SimpleNamespace(allowed=False))
    )
    tool = _tool()
    run_context = _run_context(authorization=authorization)

    results = [
        item
        async for item in FunctionToolExecutor.execute(tool, run_context)
    ]

    assert "Permission denied" in results[0].content[0].text
    authorization.authorize.assert_awaited_once()
    tool.handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_execution_calls_handler_after_authorization():
    authorization = SimpleNamespace(
        authorize=AsyncMock(return_value=SimpleNamespace(allowed=True))
    )
    tool = _tool()
    run_context = _run_context(authorization=authorization)

    results = [
        item
        async for item in FunctionToolExecutor.execute(tool, run_context)
    ]

    assert len(results) == 1
    assert results[0].content[0].text == "ok"
    tool.handler.assert_awaited_once()
