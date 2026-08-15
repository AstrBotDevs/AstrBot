import asyncio
from types import SimpleNamespace

import pytest

from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.llm_types import LLMResponse, ProviderRequest
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.agent.tool import FunctionTool, ToolSet, get_tool_id
from astrbot.core.agent.tool_image_cache import ToolImageCache
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
from tests.fixtures.auth import attach_authorized_tool_context


class _Preferences:
    def __init__(self, value: dict) -> None:
        self.value = value

    async def global_get(self, key: str, default=None):
        return self.value if key == "tool_parallel_execution" else default


class _Event:
    def get_result(self):
        return None


def _make_runner(tmp_path, preferences: _Preferences) -> ToolLoopAgentRunner:
    runner = ToolLoopAgentRunner(ToolImageCache(tmp_path / "tool-images"))
    runner.tool_schema_mode = "full"
    runner._skill_like_raw_tool_set = None
    runner._tool_call_history = []
    runner._last_tool_name = None
    runner._last_tool_args = None
    runner._same_tool_streak = 0
    runner._pending_follow_ups = []
    runner._abort_signal = asyncio.Event()
    runner._aborted = False
    event = _Event()
    runtime = SimpleNamespace(preferences=preferences)
    attach_authorized_tool_context(event, runtime, "session.read")
    runner.run_context = ContextWrapper(
        context=SimpleNamespace(context=runtime, event=event)
    )
    runner.tool_executor = FunctionToolExecutor()
    runner.agent_hooks = BaseAgentRunHooks()
    runner.tool_result_overflow_dir = None
    runner.read_tool = None
    return runner


@pytest.mark.asyncio
async def test_parallel_tools_overlap_and_preserve_result_order(tmp_path):
    started = 0
    both_started = asyncio.Event()
    release = asyncio.Event()

    async def handler(_event, value: str):
        nonlocal started
        started += 1
        if started == 2:
            both_started.set()
        await release.wait()
        return f"result-{value}"

    tools = [
        FunctionTool(
            name="read_a",
            description="read a",
            parameters={"type": "object", "properties": {"value": {"type": "string"}}},
            handler=handler,
            handler_module_path="tests.parallel_tools",
            parallel_policy="safe",
            required_actions=("session.read",),
        ),
        FunctionTool(
            name="read_b",
            description="read b",
            parameters={"type": "object", "properties": {"value": {"type": "string"}}},
            handler=handler,
            handler_module_path="tests.parallel_tools",
            parallel_policy="safe",
            required_actions=("session.read",),
        ),
    ]
    preferences = _Preferences(
        {
            "enabled": True,
            "allowed_tool_ids": [get_tool_id(tool) for tool in tools],
            "max_calls": 8,
        }
    )
    runner = _make_runner(tmp_path, preferences)
    request = ProviderRequest(func_tool=ToolSet(tools=tools), contexts=[])
    response = LLMResponse(
        role="assistant",
        tools_call_name=["read_a", "read_b"],
        tools_call_args=[{"value": "a"}, {"value": "b"}],
        tools_call_ids=["call-a", "call-b"],
    )

    async def collect_results():
        return [item async for item in runner._handle_function_tools(request, response)]

    task = asyncio.create_task(collect_results())
    await asyncio.wait_for(both_started.wait(), timeout=1)
    release.set()
    results = await task
    blocks = next(
        item.tool_call_result_blocks
        for item in results
        if item.kind == "tool_call_result_blocks"
    )
    assert [block.tool_call_id for block in blocks] == ["call-a", "call-b"]
    assert "result-a" in str(blocks[0].content)
    assert "result-b" in str(blocks[1].content)


@pytest.mark.asyncio
async def test_parallel_feature_requires_explicit_tool_allowlist(tmp_path):
    calls: list[str] = []

    async def handler(_event, value: str):
        calls.append(value)
        return value

    tools = [
        FunctionTool(
            name="read_a",
            description="read a",
            parameters={"type": "object", "properties": {"value": {"type": "string"}}},
            handler=handler,
            handler_module_path="tests.parallel_tools",
            parallel_policy="safe",
            required_actions=("session.read",),
        ),
        FunctionTool(
            name="read_b",
            description="read b",
            parameters={"type": "object", "properties": {"value": {"type": "string"}}},
            handler=handler,
            handler_module_path="tests.parallel_tools",
            parallel_policy="safe",
            required_actions=("session.read",),
        ),
    ]
    runner = _make_runner(
        tmp_path,
        _Preferences({"enabled": True, "allowed_tool_ids": [], "max_calls": 8}),
    )
    request = ProviderRequest(func_tool=ToolSet(tools=tools), contexts=[])
    response = LLMResponse(
        role="assistant",
        tools_call_name=["read_a", "read_b"],
        tools_call_args=[{"value": "a"}, {"value": "b"}],
        tools_call_ids=["call-a", "call-b"],
    )

    assert await runner._can_parallelize_function_tools(request, response) is False


@pytest.mark.asyncio
async def test_parallel_stop_cancels_the_batch(tmp_path):
    started = asyncio.Event()

    async def handler(_event, value: str):
        del value
        started.set()
        await asyncio.Future()

    tools = [
        FunctionTool(
            name=f"read_{suffix}",
            description="read",
            parameters={"type": "object", "properties": {"value": {"type": "string"}}},
            handler=handler,
            handler_module_path="tests.parallel_tools",
            parallel_policy="safe",
            required_actions=("session.read",),
        )
        for suffix in ("a", "b")
    ]
    runner = _make_runner(
        tmp_path,
        _Preferences(
            {
                "enabled": True,
                "allowed_tool_ids": [get_tool_id(tool) for tool in tools],
                "max_calls": 8,
            }
        ),
    )
    request = ProviderRequest(func_tool=ToolSet(tools=tools), contexts=[])
    response = LLMResponse(
        role="assistant",
        tools_call_name=["read_a", "read_b"],
        tools_call_args=[{"value": "a"}, {"value": "b"}],
        tools_call_ids=["call-a", "call-b"],
    )

    async def collect_results():
        return [
            item
            async for item in runner._handle_parallel_function_tools(request, response)
        ]

    task = asyncio.create_task(collect_results())
    await asyncio.wait_for(started.wait(), timeout=1)
    runner._abort_signal.set()
    with pytest.raises(Exception, match="interrupted"):
        await task
