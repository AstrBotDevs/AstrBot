from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from mcp.types import CallToolResult, TextContent

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_hooks import MainAgentHooks
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.star.star_handler import EventType


def _build_run_context(*, sdk_plugin_bridge=None):
    event = MagicMock()
    context = SimpleNamespace(
        event=event,
        context=SimpleNamespace(sdk_plugin_bridge=sdk_plugin_bridge),
    )
    return ContextWrapper(context=context), event


@pytest.mark.asyncio
async def test_main_agent_hooks_dispatches_agent_begin_to_sdk() -> None:
    sdk_plugin_bridge = SimpleNamespace(dispatch_message_event=AsyncMock())
    hooks = MainAgentHooks()
    run_context, event = _build_run_context(sdk_plugin_bridge=sdk_plugin_bridge)

    await hooks.on_agent_begin(run_context)

    sdk_plugin_bridge.dispatch_message_event.assert_awaited_once_with(
        "agent_begin",
        event,
    )


@pytest.mark.asyncio
async def test_main_agent_hooks_dispatches_agent_done_to_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_plugin_bridge = SimpleNamespace(dispatch_message_event=AsyncMock())
    hooks = MainAgentHooks()
    run_context, event = _build_run_context(sdk_plugin_bridge=sdk_plugin_bridge)
    llm_response = LLMResponse(
        role="assistant",
        completion_text="reply text",
        reasoning_content="thinking",
        tools_call_name=["search_docs"],
    )
    call_event_hook_mock = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "astrbot.core.astr_agent_hooks.call_event_hook",
        call_event_hook_mock,
    )

    await hooks.on_agent_done(run_context, llm_response)

    event.set_extra.assert_called_once_with("_llm_reasoning_content", "thinking")
    assert call_event_hook_mock.await_args_list == [
        call(event, EventType.OnLLMResponseEvent, llm_response),
        call(event, EventType.OnAgentDoneEvent, run_context, llm_response),
    ]
    assert sdk_plugin_bridge.dispatch_message_event.await_count == 2
    first_call = sdk_plugin_bridge.dispatch_message_event.await_args_list[0]
    assert first_call.args == (
        "llm_response",
        event,
        {
            "completion_text": "reply text",
        },
    )
    assert first_call.kwargs == {"llm_response": llm_response}
    second_call = sdk_plugin_bridge.dispatch_message_event.await_args_list[1]
    assert second_call.args == (
        "agent_done",
        event,
        {
            "completion_text": "reply text",
            "tool_call_names": ["search_docs"],
        },
    )
    assert second_call.kwargs == {"llm_response": llm_response}


@pytest.mark.asyncio
async def test_main_agent_hooks_dispatches_tool_start_to_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_plugin_bridge = SimpleNamespace(dispatch_message_event=AsyncMock())
    hooks = MainAgentHooks()
    run_context, event = _build_run_context(sdk_plugin_bridge=sdk_plugin_bridge)
    tool = FunctionTool(
        name="search_docs",
        description="Search documents",
        parameters={"type": "object", "properties": {}},
        handler=AsyncMock(),
    )
    tool_args = {"query": "sdk"}
    call_event_hook_mock = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "astrbot.core.astr_agent_hooks.call_event_hook",
        call_event_hook_mock,
    )

    await hooks.on_tool_start(run_context, tool, tool_args)

    call_event_hook_mock.assert_awaited_once_with(
        event,
        EventType.OnUsingLLMToolEvent,
        tool,
        tool_args,
    )
    sdk_plugin_bridge.dispatch_message_event.assert_awaited_once_with(
        "llm_tool_start",
        event,
        {
            "tool_name": "search_docs",
            "tool_args": {"query": "sdk"},
        },
    )


@pytest.mark.asyncio
async def test_main_agent_hooks_dispatches_tool_end_to_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_plugin_bridge = SimpleNamespace(dispatch_message_event=AsyncMock())
    hooks = MainAgentHooks()
    run_context, event = _build_run_context(sdk_plugin_bridge=sdk_plugin_bridge)
    tool = FunctionTool(
        name="search_docs",
        description="Search documents",
        parameters={"type": "object", "properties": {}},
        handler=AsyncMock(),
    )
    tool_args = {"query": "sdk"}
    tool_result = CallToolResult(
        content=[TextContent(type="text", text="matched docs")]
    )
    call_event_hook_mock = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "astrbot.core.astr_agent_hooks.call_event_hook",
        call_event_hook_mock,
    )

    await hooks.on_tool_end(run_context, tool, tool_args, tool_result)

    event.clear_result.assert_called_once_with()
    call_event_hook_mock.assert_awaited_once_with(
        event,
        EventType.OnLLMToolRespondEvent,
        tool,
        tool_args,
        tool_result,
    )
    sdk_plugin_bridge.dispatch_message_event.assert_awaited_once()
    event_type, dispatched_event, payload = (
        sdk_plugin_bridge.dispatch_message_event.await_args.args
    )
    assert event_type == "llm_tool_end"
    assert dispatched_event is event
    assert payload["tool_name"] == "search_docs"
    assert payload["tool_args"] == {"query": "sdk"}
    assert payload["tool_result"]["isError"] is False
    assert payload["tool_result"]["content"][0]["type"] == "text"
    assert payload["tool_result"]["content"][0]["text"] == "matched docs"
