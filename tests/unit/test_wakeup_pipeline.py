"""Wakeup regressions using the real bus, pipeline, request collector, and runner."""

import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from opentelemetry.trace import format_trace_id, get_current_span

from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolSet
from astrbot.core.astr_agent_run_util import AgentRunner
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
from astrbot.core.astr_agent_wakeup import wake_main_agent
from astrbot.core.astr_main_agent import MainAgentBuildResult
from astrbot.core.astr_main_agent.request import prepare_request
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.event_bus import EventBus
from astrbot.core.log import _log_context
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.pipeline.context import PipelineContext
from astrbot.core.pipeline.process_stage.method.agent_sub_stages import internal
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.platform.astr_message_event import (
    AstrMessageEvent,
    current_message_event,
)
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.tools.message_tools import SendMessageToUserTool
from astrbot.core.utils import trace as trace_module
from astrbot.dashboard.services.conversation_service import ConversationService


@pytest_asyncio.fixture
async def runtime(monkeypatch):
    """Wire real execution components to an offline provider and in-memory history.

    Args:
        monkeypatch: Patch manager for external services and background metrics.

    Yields:
        Controls for provider execution, delivery, and pipeline completion.
    """
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["provider_settings"]["streaming_response"] = False
    config["provider_settings"]["wake_prefix"] = "/llm "
    config["platform_settings"]["unique_session"] = True
    config["admins_id"] = ["astrbot"]
    conversation = SimpleNamespace(cid="conversation", history="[]", token_usage=0)
    queue = asyncio.Queue()
    metadata = PlatformMetadata(id="target", name="aiocqhttp", description="Target")
    control = SimpleNamespace(
        started=asyncio.Event(),
        gate=asyncio.Event(),
        cleaned=asyncio.Event(),
        requests=[],
        events=[],
        runners=[],
        deliver=False,
        tool_delivery=False,
        completion=None,
        delivered=asyncio.Event(),
        after_delivery=asyncio.Event(),
        fail=False,
    )
    control.gate.set()
    control.after_delivery.set()

    async def save(*args, **kwargs):
        conversation.history = json.dumps(kwargs["history"])

    context = SimpleNamespace(
        get_event_queue=lambda: queue,
        get_platform_inst=lambda _: SimpleNamespace(meta=lambda: metadata),
        get_config=lambda **_: config,
        conversation_manager=SimpleNamespace(
            get_curr_conversation_id=AsyncMock(return_value=conversation.cid),
            get_conversation=AsyncMock(return_value=conversation),
            update_conversation=AsyncMock(side_effect=save),
        ),
        get_using_tts_provider_async=AsyncMock(return_value=None),
        send_message=AsyncMock(return_value=True),
    )

    async def respond(**kwargs):
        event = current_message_event.get()
        assert _log_context.get().platform_id == "target"
        assert (
            format_trace_id(get_current_span().get_span_context().trace_id)
            == event.trace.trace_id
        )
        control.requests.append(kwargs["contexts"])
        control.started.set()
        try:
            await control.gate.wait()
            if control.tool_delivery and len(control.requests) == 1:
                return LLMResponse(
                    role="assistant",
                    tools_call_name=["send_message_to_user"],
                    tools_call_args=[
                        {"messages": [{"type": "plain", "text": "Take your medicine"}]}
                    ],
                    tools_call_ids=["reminder"],
                )
            if control.tool_delivery and len(control.requests) == 2:
                control.delivered.set()
                await control.after_delivery.wait()
            if control.deliver:
                await event.send(MessageChain().message("Explicit delivery"))
            return LLMResponse(
                role="err" if control.fail else "assistant",
                completion_text=(
                    control.completion
                    if control.completion is not None
                    else f"Reply {len(control.requests)}"
                ),
            )
        finally:
            control.cleaned.set()

    async def respond_stream(**kwargs):
        response = await respond(**kwargs)
        if response.role != "err" and response.completion_text:
            for text in (response.completion_text[:3], response.completion_text[3:]):
                yield LLMResponse(role="assistant", completion_text=text, is_chunk=True)
        yield response

    provider = SimpleNamespace(
        provider_config={"id": "offline", "modalities": ["text"]},
        get_model=lambda: "offline",
        meta=lambda: SimpleNamespace(type="test"),
        text_chat=respond,
        text_chat_stream=respond_stream,
    )

    async def build(*, event, plugin_context, config):
        prepared = await prepare_request(event, plugin_context, config, provider, None)
        assert prepared is not None
        control.events.append(event)
        if control.tool_delivery:
            prepared.request.func_tool = ToolSet([SendMessageToUserTool()])
        runner = AgentRunner()
        await runner.reset(
            provider=provider,
            request=prepared.request,
            run_context=ContextWrapper(
                context=SimpleNamespace(event=event, context=context)
            ),
            tool_executor=FunctionToolExecutor,
            agent_hooks=BaseAgentRunHooks(),
            streaming=config.streaming_response,
        )
        control.runners.append(runner)
        return MainAgentBuildResult(runner, prepared.request, provider)

    monkeypatch.setattr(internal, "build_main_agent", build)
    monkeypatch.setattr(internal, "_record_internal_agent_stats", AsyncMock())
    monkeypatch.setattr(internal.Metric, "upload", AsyncMock())
    monkeypatch.setattr(
        internal.SessionServiceManager,
        "should_process_llm_request",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        internal.SessionServiceManager,
        "is_session_enabled",
        AsyncMock(return_value=True),
    )
    monkeypatch.setitem(trace_module.astrbot_config, "trace_enable", True)
    monkeypatch.setattr(
        trace_module,
        "get_trace_store",
        lambda *_: SimpleNamespace(append=lambda *args, **kwargs: True),
    )
    monkeypatch.setattr(trace_module, "_get_log_broker", lambda: None)
    scheduler = PipelineScheduler(
        PipelineContext(config, SimpleNamespace(context=context), "profile")
    )
    await scheduler.initialize()
    bus = EventBus(
        queue,
        {"profile": scheduler},
        SimpleNamespace(get_conf_info=lambda _: {"id": "profile"}),
    )
    dispatcher = asyncio.create_task(bus.dispatch())

    async def drain():
        while not queue.empty() or bus._pending_tasks:
            await asyncio.sleep(0)
            await asyncio.gather(*list(bus._pending_tasks), return_exceptions=True)

    control.context, control.conversation = context, conversation
    control.bus, control.scheduler, control.drain = bus, scheduler, drain
    control.agent_stage = next(
        s for s in scheduler.stages if type(s).__name__ == "ProcessStage"
    ).agent_sub_stage.agent_sub_stage
    yield control
    dispatcher.cancel()
    pending = [dispatcher, *bus._pending_tasks]
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("deliver", [False, True])
@pytest.mark.parametrize("streaming", [False, True])
async def test_wakeup_uses_current_context_and_sends_final_reply(
    runtime, deliver, streaming
):
    """Keep routing, execution scopes, history, and delivery on the normal path."""
    runtime.deliver = deliver
    runtime.agent_stage.streaming_response = streaming
    history = [{"role": "user", "content": "Existing context"}]
    runtime.conversation.history = json.dumps(history)
    umo = "target:GroupMessage:user_group"
    await wake_main_agent(
        runtime.context, umo=umo, user_prompt="Continue", source="cron"
    )
    await asyncio.wait_for(runtime.drain(), 1)
    event = runtime.events[0]
    assert event.unified_msg_origin == umo
    assert event.role == "member"
    assert runtime.requests[0][0] == history[0]
    assert json.loads(runtime.conversation.history) == history + [
        {"role": "user", "content": [{"type": "text", "text": "Continue"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Reply 1"}]},
    ]
    delivered_texts = [
        call.args[1].get_plain_text()
        for call in runtime.context.send_message.await_args_list
    ]
    assert delivered_texts == (["Explicit delivery"] if deliver else []) + ["Reply 1"]
    assert event.trace._summary["state"] == "completed"
    assert not event.trace._summary["has_errors"]
    assert current_message_event.get() is None and _log_context.get() is None


@pytest.mark.asyncio
async def test_wakeup_runs_normal_whitelist_check(runtime):
    """Reject a target before constructing an agent when the allowlist denies it."""
    stage = next(
        s for s in runtime.scheduler.stages if type(s).__name__ == "WhitelistCheckStage"
    )
    stage.enable_whitelist_check = True
    stage.whitelist = ["another:FriendMessage:user"]
    await wake_main_agent(
        runtime.context,
        umo="target:FriendMessage:user",
        user_prompt="Run",
        source="plugin",
    )
    await asyncio.wait_for(runtime.drain(), 1)
    assert not runtime.events
    runtime.context.conversation_manager.get_conversation.assert_not_awaited()


@pytest.mark.asyncio
async def test_wakeup_queues_after_an_active_message_and_reads_its_saved_reply(runtime):
    """Return immediately from enqueueing and load history after the session lock."""
    runtime.gate.clear()
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.self_id = "bot"
    message.sender = MessageMember(user_id="alice")
    message.message = []
    first = AstrMessageEvent(
        "/llm First input",
        message,
        PlatformMetadata(id="target", name="aiocqhttp", description="Target"),
        "user",
    )
    await runtime.context.get_event_queue().put(first)
    await asyncio.wait_for(runtime.started.wait(), 1)
    await asyncio.wait_for(
        wake_main_agent(
            runtime.context,
            umo=first.unified_msg_origin,
            user_prompt="Next input",
            source="background_task",
        ),
        1,
    )
    for _ in range(20):
        await asyncio.sleep(0)
    assert len(runtime.requests) == 1
    runtime.gate.set()
    await asyncio.wait_for(runtime.drain(), 1)
    assert len(runtime.requests) == 2
    assert {
        "role": "assistant",
        "content": [{"type": "text", "text": "Reply 1"}],
    } in runtime.requests[1]
    assert json.loads(runtime.conversation.history)[-1]["content"] == [
        {"type": "text", "text": "Reply 2"}
    ]


@pytest.mark.asyncio
async def test_platform_stop_cancels_the_wakeup_provider_and_preserves_history(runtime):
    """Finish provider cleanup through the ordinary event-bus cancellation path."""
    runtime.gate.clear()
    await wake_main_agent(
        runtime.context,
        umo="target:FriendMessage:user",
        user_prompt="Run",
        source="cron",
    )
    await asyncio.wait_for(runtime.started.wait(), 1)
    await runtime.bus.stop_platform("target")
    assert runtime.cleaned.is_set()
    assert not runtime.bus._pending_tasks
    runtime.context.conversation_manager.update_conversation.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_wakeup_failure_is_traced_and_delivered(runtime, streaming):
    """Deliver the provider error while retaining the failed trace and history."""
    runtime.fail = True
    runtime.agent_stage.streaming_response = streaming
    await wake_main_agent(
        runtime.context,
        umo="target:FriendMessage:user",
        user_prompt="Run",
        source="plugin",
    )
    await asyncio.wait_for(runtime.drain(), 1)
    assert runtime.events[0].trace._summary["has_errors"]
    runtime.context.send_message.assert_awaited_once()
    assert (
        runtime.context.send_message.await_args.args[1].get_plain_text()
        == "LLM 响应错误: Reply 1"
    )
    runtime.context.conversation_manager.update_conversation.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["completed", "cancelled", "failed"])
@pytest.mark.parametrize("streaming", [False, True])
async def test_proactive_tool_delivery_is_saved_before_wakeup_finishes(
    runtime, outcome, streaming
):
    """Retain delivered text while the agent is still running and after it exits."""
    runtime.tool_delivery = True
    runtime.after_delivery.clear()
    runtime.fail = outcome == "failed"
    runtime.agent_stage.streaming_response = streaming
    await wake_main_agent(
        runtime.context,
        umo="target:FriendMessage:user",
        user_prompt="Send a reminder",
        source="cron",
    )
    await asyncio.wait_for(runtime.delivered.wait(), 1)
    delivered = {"role": "assistant", "content": "Take your medicine"}
    before_completion = json.loads(runtime.conversation.history)
    if outcome == "cancelled":
        await runtime.bus.stop_platform("target")
    else:
        runtime.after_delivery.set()
        await asyncio.wait_for(runtime.drain(), 1)
    assert delivered in before_completion
    history = json.loads(runtime.conversation.history)
    if outcome == "completed":
        assert history.count(delivered) == 1
        assert "Take your medicine" in json.dumps(history)
        assert any(message["role"] == "tool" for message in history)
    else:
        assert history.count(delivered) == 1


@pytest.mark.asyncio
async def test_reply_to_running_wakeup_waits_and_sees_delivered_text(runtime):
    """Serialize a quick user reply and preserve the actual reminder in its context."""
    runtime.tool_delivery = True
    runtime.after_delivery.clear()
    await wake_main_agent(
        runtime.context,
        umo="target:FriendMessage:user",
        user_prompt="Send a reminder",
        source="cron",
    )
    await asyncio.wait_for(runtime.delivered.wait(), 1)
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.self_id = "bot"
    message.sender = MessageMember(user_id="alice")
    message.message = []
    reply = AstrMessageEvent(
        "/llm Already taken",
        message,
        PlatformMetadata(id="target", name="aiocqhttp", description="Target"),
        "user",
    )
    await runtime.context.get_event_queue().put(reply)
    for _ in range(20):
        await asyncio.sleep(0)
    assert len(runtime.requests) == 2
    runtime.after_delivery.set()
    await asyncio.wait_for(runtime.drain(), 1)
    assert len(runtime.requests) == 3
    assert "Take your medicine" in json.dumps(runtime.requests[2])
    assert {"role": "assistant", "content": "Take your medicine"} in runtime.requests[2]


@pytest.mark.asyncio
async def test_dashboard_history_edit_waits_for_the_running_wakeup(runtime):
    """Apply a dashboard edit after the agent snapshot so completion cannot erase it."""
    runtime.gate.clear()
    await wake_main_agent(
        runtime.context,
        umo="target:FriendMessage:user",
        user_prompt="Run",
        source="cron",
    )
    await asyncio.wait_for(runtime.started.wait(), 1)
    service = ConversationService(MagicMock(), runtime.context)
    edited_history = [{"role": "assistant", "content": "Dashboard edit"}]
    editing = asyncio.create_task(
        service.update_history(
            {
                "user_id": "target:FriendMessage:user",
                "cid": runtime.conversation.cid,
                "history": edited_history,
            }
        )
    )
    for _ in range(20):
        await asyncio.sleep(0)
    was_pending = not editing.done()
    runtime.gate.set()
    await asyncio.wait_for(runtime.drain(), 1)
    await asyncio.wait_for(editing, 1)
    assert was_pending
    assert json.loads(runtime.conversation.history) == edited_history


@pytest.mark.asyncio
@pytest.mark.parametrize("completion", ["Take your medicine", ""])
async def test_tool_delivery_survives_duplicate_or_empty_final_reply(
    runtime, completion
):
    """Keep exactly one assistant record when the final reply adds no new text."""
    runtime.tool_delivery = True
    runtime.completion = completion
    await wake_main_agent(
        runtime.context,
        umo="target:FriendMessage:user",
        user_prompt="Send a reminder",
        source="background_task",
    )
    await asyncio.wait_for(runtime.drain(), 1)
    history = json.loads(runtime.conversation.history)
    texts = [
        message["content"]
        if isinstance(message["content"], str)
        else "".join(part.get("text", "") for part in (message["content"] or []))
        for message in history
        if message["role"] == "assistant"
    ]
    assert texts.count("Take your medicine") == 1
    assert [
        call.args[1].get_plain_text()
        for call in runtime.context.send_message.await_args_list
    ] == ["Take your medicine"]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["read", "write"])
async def test_platform_stop_waits_for_confirmed_delivery_to_be_persisted(
    runtime, operation
):
    """Do not release the pipeline lock while a confirmed delivery write is pending."""
    runtime.tool_delivery = True
    runtime.gate.clear()
    await wake_main_agent(
        runtime.context,
        umo="target:FriendMessage:user",
        user_prompt="Send a reminder",
        source="cron",
    )
    await asyncio.wait_for(runtime.started.wait(), 1)
    manager = runtime.context.conversation_manager
    entered, release = asyncio.Event(), asyncio.Event()
    original_save = manager.update_conversation.side_effect

    async def blocked(*args, **kwargs):
        entered.set()
        await release.wait()
        if operation == "read":
            return runtime.conversation
        await original_save(*args, **kwargs)

    if operation == "read":
        manager.get_conversation.side_effect = blocked
    else:
        manager.update_conversation.side_effect = blocked
    runtime.gate.set()
    await asyncio.wait_for(entered.wait(), 1)
    stopping = asyncio.create_task(runtime.bus.stop_platform("target"))
    for _ in range(20):
        await asyncio.sleep(0)
    was_pending = not stopping.done()
    release.set()
    await asyncio.wait_for(stopping, 1)
    assert was_pending
    assert json.loads(runtime.conversation.history) == [
        {"role": "assistant", "content": "Take your medicine"}
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing_platform", "transport", "storage"])
async def test_proactive_delivery_distinguishes_send_and_storage_failures(
    runtime, failure
):
    """Only confirmed text becomes assistant history; storage failure never resends."""
    runtime.tool_delivery = True
    if failure == "missing_platform":
        runtime.context.send_message.return_value = False
    elif failure == "transport":
        runtime.context.send_message.side_effect = RuntimeError("Transport unavailable")
    else:
        runtime.context.conversation_manager.update_conversation.side_effect = (
            RuntimeError("Storage unavailable")
        )
    await wake_main_agent(
        runtime.context,
        umo="target:FriendMessage:user",
        user_prompt="Send a reminder",
        source="cron",
    )
    await asyncio.wait_for(runtime.drain(), 1)
    results = [
        message
        for message in runtime.runners[0].run_context.messages
        if message.role == "tool"
    ]
    assert len(results) == 1
    if failure == "storage":
        assert results[0].content.startswith("Message sent to session")
    else:
        assert results[0].content.startswith("error:")
    deliveries = [
        call
        for call in runtime.context.send_message.await_args_list
        if call.args[1].get_plain_text() == "Take your medicine"
    ]
    assert len(deliveries) == 1
    assert {"role": "assistant", "content": "Take your medicine"} not in json.loads(
        runtime.conversation.history
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["switched", "deleted"])
async def test_proactive_delivery_stays_bound_to_its_original_conversation(
    runtime, change
):
    """Never redirect a delivery to a newly selected or replacement conversation."""
    runtime.tool_delivery = True
    runtime.gate.clear()
    runtime.after_delivery.clear()
    await wake_main_agent(
        runtime.context,
        umo="target:FriendMessage:user",
        user_prompt="Send a reminder",
        source="cron",
    )
    await asyncio.wait_for(runtime.started.wait(), 1)
    manager = runtime.context.conversation_manager
    manager.get_curr_conversation_id.return_value = "another-conversation"
    if change == "deleted":
        manager.get_conversation.return_value = None
    runtime.gate.set()
    await asyncio.wait_for(runtime.delivered.wait(), 1)
    manager.get_conversation.assert_awaited_with(
        "target:FriendMessage:user", "conversation"
    )
    await runtime.bus.stop_platform("target")
    if change == "deleted":
        manager.update_conversation.assert_not_awaited()
    else:
        manager.update_conversation.assert_awaited_once_with(
            "target:FriendMessage:user",
            "conversation",
            history=[{"role": "assistant", "content": "Take your medicine"}],
        )
