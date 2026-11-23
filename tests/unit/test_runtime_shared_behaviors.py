"""Behavior boundaries for shared agent and computer runtime operations."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mcp.types import CallToolResult, TextContent

from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.base import AgentState
from astrbot.core.agent.runners.coze.coze_agent_runner import CozeAgentRunner
from astrbot.core.agent.runners.dashscope.dashscope_agent_runner import (
    DashscopeAgentRunner,
)
from astrbot.core.agent.runners.deerflow.deerflow_agent_runner import (
    DeerFlowAgentRunner,
)
from astrbot.core.agent.runners.deerflow.deerflow_api_client import _stream_sse
from astrbot.core.agent.runners.dify.dify_agent_runner import DifyAgentRunner
from astrbot.core.agent.runners.tool_loop_agent_runner import (
    FollowUpTicket,
    ToolLoopAgentRunner,
)
from astrbot.core.astr_agent_runtime.computer.booters.cua import (
    CuaFileSystemComponent,
    _PosixShellFileSystem,
)
from astrbot.core.astr_agent_runtime.computer.booters.shipyard_neo import (
    NeoFileSystemComponent,
)
from astrbot.core.astr_agent_runtime.tool_executor import _accumulate_tool_result
from astrbot.core.astr_agent_runtime.tools import web_search_tools
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import ProviderRequest

REMOTE_RUNNERS = [
    (CozeAgentRunner, "_execute_coze_request"),
    (DifyAgentRunner, "_execute_dify_request"),
    (DashscopeAgentRunner, "_execute_dashscope_request"),
    (DeerFlowAgentRunner, "_execute_deerflow_request"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("runner_type,execute_name", REMOTE_RUNNERS)
async def test_remote_hooks_keep_state_order_and_tolerate_hook_errors(
    monkeypatch, runner_type, execute_name
):
    runner = runner_type()
    observed = []

    class Hooks(BaseAgentRunHooks):
        async def on_agent_begin(self, context):
            observed.append(("begin", runner.state))
            raise RuntimeError("broken begin observer")

        async def on_llm_response(self, context, response):
            observed.append((response.result_chain.get_plain_text(), runner.state))
            raise RuntimeError("broken response observer")

        async def on_agent_done(self, context, response):
            observed.append(("done", runner.state))
            raise RuntimeError("broken cleanup observer")

    runner._reset_request(
        ProviderRequest(prompt="hello"), ContextWrapper(context=None), Hooks(), False
    )
    runner.api_client = SimpleNamespace(close=AsyncMock())

    async def response():
        yield await runner._finish_with_result(MessageChain().message("answer"))

    monkeypatch.setattr(runner, execute_name, response)
    events = [event async for event in runner.step()]
    assert observed == [
        ("begin", AgentState.IDLE),
        ("answer", AgentState.DONE),
        ("done", AgentState.DONE),
    ]
    assert [event.type for event in events] == ["llm_result"]
    assert events[0].data["chain"].get_plain_text() == "answer"
    assert runner.done()


@pytest.mark.asyncio
@pytest.mark.parametrize("runner_type,execute_name", REMOTE_RUNNERS)
async def test_remote_begin_cancellation_never_executes_a_service_request(
    monkeypatch, runner_type, execute_name
):
    runner = runner_type()
    hooks = AsyncMock(spec=BaseAgentRunHooks)
    hooks.on_agent_begin.side_effect = asyncio.CancelledError
    runner._reset_request(
        ProviderRequest(prompt="hello"), ContextWrapper(context=None), hooks, False
    )
    calls = []

    async def response():
        calls.append("request")
        yield await runner._finish_with_result(MessageChain().message("unexpected"))

    monkeypatch.setattr(runner, execute_name, response)
    with pytest.raises(asyncio.CancelledError):
        await anext(runner.step())
    assert not calls
    assert runner.state is AgentState.IDLE
    assert runner.get_final_llm_resp() is None
    hooks.on_agent_done.assert_not_awaited()


@pytest.mark.asyncio
async def test_follow_up_arriving_during_persistence_waits_for_next_boundary():
    runner = ToolLoopAgentRunner()
    first = FollowUpTicket(seq=1, text="first")
    later = FollowUpTicket(seq=2, text="later")
    runner._pending_follow_ups = [first]
    runner._steering_signal = asyncio.Event()
    runner._steering_signal.set()
    entered, release = asyncio.Event(), asyncio.Event()
    persisted = []

    async def append(messages):
        entered.set()
        await release.wait()
        persisted.extend(messages)

    runner._append_context_messages = append
    consuming = asyncio.create_task(runner._consume_pending_follow_ups())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        runner._pending_follow_ups.append(later)
        release.set()
        await asyncio.wait_for(consuming, 2)
        assert first.consumed and first.resolved.is_set()
        assert not later.consumed and not later.resolved.is_set()
        assert runner._pending_follow_ups == [later]
        assert runner._steering_signal.is_set()
        await runner._consume_pending_follow_ups()
        assert later.consumed and later.resolved.is_set()
        assert not runner._steering_signal.is_set()
        assert [message.content[0].text for message in persisted] == ["first", "later"]
    finally:
        consuming.cancel()
        await asyncio.gather(consuming, return_exceptions=True)


@pytest.mark.asyncio
async def test_sse_preserves_lazy_order_split_utf8_and_final_unterminated_event():
    consumed = []

    class Content:
        async def iter_chunked(self, size):
            assert size == 8192
            for chunk in (
                b'data: {"n": 1}\n\ndata: {"n": 2}\n\n',
                b'data: {"text": "\xe4',
                b'\xb8\xad"}\n\n: heartbeat\n\ndata: tail',
            ):
                consumed.append(chunk)
                yield chunk

    stream = _stream_sse(SimpleNamespace(content=Content()))
    try:
        assert await anext(stream) == {"event": "message", "data": {"n": 1}}
        assert len(consumed) == 1
        assert await anext(stream) == {"event": "message", "data": {"n": 2}}
        assert len(consumed) == 1
        assert [event async for event in stream] == [
            {"event": "message", "data": {"text": "中"}},
            {"event": "message", "data": "tail"},
        ]
    finally:
        await stream.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "component_type",
    [CuaFileSystemComponent, _PosixShellFileSystem, NeoFileSystemComponent],
)
@pytest.mark.parametrize(
    "mode", ["first", "all", "missing", "read_error", "write_error"]
)
async def test_remote_edit_preserves_adapter_envelopes_and_write_count(
    monkeypatch, component_type, mode
):
    component = component_type.__new__(component_type)
    read_result = {"success": mode != "read_error", "content": "red red"}
    write_result = {"success": mode != "write_error", "error": "write denied"}
    reader = AsyncMock(return_value=read_result)
    writer = AsyncMock(return_value=write_result)
    monkeypatch.setattr(component, "read_file", reader)
    monkeypatch.setattr(component, "write_file", writer)
    result = await component.edit_file(
        "/work/name.txt",
        "missing" if mode == "missing" else "red",
        "blue",
        replace_all=mode == "all",
    )
    reader.assert_awaited_once_with("/work/name.txt", encoding="utf-8")
    if mode == "read_error":
        assert result is read_result
        writer.assert_not_awaited()
    elif mode == "missing":
        assert result["success"] is False and result["replacements"] == 0
        assert ("path" in result) is (component_type is not CuaFileSystemComponent)
        writer.assert_not_awaited()
    else:
        writer.assert_awaited_once_with(
            "/work/name.txt",
            "blue blue" if mode == "all" else "blue red",
            encoding="utf-8",
        )
        if mode == "write_error":
            assert result is write_result
        else:
            assert result == {
                "success": True,
                "path": "/work/name.txt",
                "replacements": 2 if mode == "all" else 1,
            }


def test_tool_chunks_keep_all_content_errors_and_latest_structured_payload():
    combined = CallToolResult(content=[])
    for chunk in (
        CallToolResult(
            content=[TextContent(type="text", text="one")], structuredContent={"n": 1}
        ),
        "side-channel notice",
        CallToolResult(content=[], isError=True),
        CallToolResult(
            content=[TextContent(type="text", text="two")], structuredContent={}
        ),
    ):
        _accumulate_tool_result(combined, chunk)
    assert [part.text for part in combined.content] == ["one", "two"]
    assert combined.isError is True
    assert combined.structuredContent == {}


def test_search_formatter_accepts_structural_iterables_and_caches_favicons(monkeypatch):
    cached = []
    monkeypatch.setattr(web_search_tools.uuid, "uuid4", lambda: "abcd-remaining")
    monkeypatch.setattr(
        web_search_tools, "_cache_favicon", lambda *args: cached.append(args)
    )
    results = (
        SimpleNamespace(
            title="中文", url="https://example.test", snippet="内容", favicon="icon"
        ),
        SimpleNamespace(
            title="other", url="https://other.test", snippet="", favicon=None
        ),
    )
    encoded = web_search_tools.format_search_results(iter(results))
    assert "中文" in encoded
    payload = json.loads(encoded)
    assert [item["index"] for item in payload["results"]] == ["abcd.1", "abcd.2"]
    assert cached == [("https://example.test", "icon"), ("https://other.test", None)]
