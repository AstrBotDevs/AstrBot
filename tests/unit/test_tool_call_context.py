import asyncio
from types import SimpleNamespace

import pytest

from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.agent.tool_executor import CURRENT_TOOL_CALL_ID


@pytest.mark.asyncio
@pytest.mark.parametrize("exit_mode", ["exhaust", "error", "close", "cancel"])
async def test_recorded_tool_restores_call_context(exit_mode):
    observed = []

    async def execute(**kwargs):
        observed.append(CURRENT_TOOL_CALL_ID.get())
        yield "first"
        if exit_mode == "error":
            raise ValueError("tool failed")
        if exit_mode == "cancel":
            raise asyncio.CancelledError

    runner = ToolLoopAgentRunner()
    runner._events = SimpleNamespace(active=False)
    runner._abort_signal = asyncio.Event()
    runner.run_context = SimpleNamespace()
    runner.tool_executor = SimpleNamespace(execute=execute)
    parent = CURRENT_TOOL_CALL_ID.set("parent")
    results = runner._recorded_tool_results(SimpleNamespace(name="probe"), "child", {})
    try:
        assert await anext(results) == "first"
        if exit_mode == "close":
            await results.aclose()
        else:
            error = {
                "exhaust": StopAsyncIteration,
                "error": ValueError,
                "cancel": asyncio.CancelledError,
            }[exit_mode]
            with pytest.raises(error):
                await anext(results)
        assert observed == ["child"]
        # Without the reset in `finally`, the child id leaks the child id into its caller.
        assert CURRENT_TOOL_CALL_ID.get() == "parent"
    finally:
        await results.aclose()
        CURRENT_TOOL_CALL_ID.reset(parent)
