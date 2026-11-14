"""Wakeup regressions using the real bus, pipeline, request collector, and runner."""

import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from opentelemetry.trace import format_trace_id, get_current_span

from astrbot.core.agent.conversation_events import ConversationEventWriter
from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolSet
from astrbot.core.agent_wakeup import wake_main_agent
from astrbot.core.astr_agent_runtime import AstrAgentRuntime
from astrbot.core.astr_agent_runtime import session as native_session
from astrbot.core.astr_agent_runtime.main_agent import MainAgentBuildResult
from astrbot.core.astr_agent_runtime.main_agent import builder as native_builder
from astrbot.core.astr_agent_runtime.main_agent.request import prepare_request
from astrbot.core.astr_agent_runtime.runner import AgentRunner
from astrbot.core.astr_agent_runtime.tool_executor import FunctionToolExecutor
from astrbot.core.astr_agent_runtime.tools.message_tools import SendMessageToUserTool
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.event_bus import EventBus
from astrbot.core.log import _log_context
from astrbot.core.pipeline.context import PipelineContext
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.platform.astr_message_event import (
    AstrMessageEvent,
    current_message_event,
)
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.func_tool_manager import FunctionToolManager
from astrbot.core.utils import trace as trace_module


@pytest_asyncio.fixture
async def runtime(monkeypatch, database):
    """Wire real execution components to an offline provider and SQLite history.

    Args:
        monkeypatch: Patch manager for external services and background metrics.
        database: Isolated SQLite database with initialized event storage.

    Yields:
        Controls for provider execution, delivery, and pipeline completion.
    """
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["provider_settings"]["streaming_response"] = False
    config["provider_settings"]["wake_prefix"] = "/llm "
    config["provider_settings"]["datetime_system_prompt"] = False
    config["platform_settings"]["unique_session"] = True
    config["admins_id"] = ["astrbot"]
    store = database.conversation_store
    record = await store.create(umo="target:FriendMessage:user", platform_id="target")
    manager = ConversationManager(database)
    manager.session_conversations["target:FriendMessage:user"] = record.conversation_id
    queue = asyncio.Queue()
    metadata = PlatformMetadata(id="target", name="aiocqhttp", description="Target")
    control = SimpleNamespace(
        started=asyncio.Event(),
        gate=asyncio.Event(),
        requests=[],
        runners=[],
        completion=None,
        delivered=asyncio.Event(),
        after_delivery=asyncio.Event(),
        fail=False,
        store=store,
        cid=record.conversation_id,
    )
    control.gate.set()
    control.after_delivery.set()

    context = SimpleNamespace(
        get_event_queue=lambda: queue,
        get_platform_inst=lambda _: SimpleNamespace(meta=lambda: metadata),
        get_config=lambda **_: config,
        astrbot_config_mgr=SimpleNamespace(
            _create_message_config=lambda _: (copy.deepcopy(config), frozenset())
        ),
        conversation_manager=manager,
        get_using_tts_provider_async=AsyncMock(return_value=None),
        get_llm_tool_manager=lambda: FunctionToolManager(),
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
        await control.gate.wait()
        if len(control.requests) == 1:
            return LLMResponse(
                role="assistant",
                tools_call_name=["send_message_to_user"],
                tools_call_args=[
                    {"messages": [{"type": "plain", "text": "Take your medicine"}]}
                ],
                tools_call_ids=["reminder"],
            )
        if len(control.requests) == 2:
            control.delivered.set()
            await control.after_delivery.wait()
        return LLMResponse(
            role="err" if control.fail else "assistant",
            completion_text=(
                control.completion
                if control.completion is not None
                else f"Reply {len(control.requests)}"
            ),
        )

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

    async def build(
        *, event, plugin_context, config, req=None, collected_input=None, **kwargs
    ):
        prepared = await prepare_request(
            event, plugin_context, config, provider, req, collected_input
        )
        assert prepared is not None
        prepared.request.func_tool = ToolSet([SendMessageToUserTool()])
        writer = ConversationEventWriter(store, await store.read(record.conversation_id))
        runner = AgentRunner()
        await runner.reset(
            provider=provider,
            request=prepared.request,
            run_context=ContextWrapper(
                context=SimpleNamespace(event=event, context=context)
            ),
            tool_executor=FunctionToolExecutor,
            agent_hooks=BaseAgentRunHooks(),
            conversation_event_sink=writer.consume,
            streaming=config.streaming_response,
        )
        control.runners.append(runner)
        return MainAgentBuildResult(
            runner, prepared.request, provider, conversation_events=writer
        )

    monkeypatch.setattr(native_builder, "build_main_agent", build)
    monkeypatch.setattr(native_session, "record_agent_stats", AsyncMock())
    monkeypatch.setattr(native_session.Metric, "upload", AsyncMock())
    monkeypatch.setitem(trace_module.astrbot_config, "trace_enable", True)
    monkeypatch.setattr(
        trace_module,
        "get_trace_store",
        lambda *_: SimpleNamespace(append=lambda *args, **kwargs: True),
    )
    monkeypatch.setattr(trace_module, "_get_log_broker", lambda: None)
    native = AstrAgentRuntime(context, agent_configs=MagicMock(), subagents=MagicMock())
    runtimes = {"astrbot": native}
    scheduler = PipelineScheduler(
        PipelineContext(
            config, SimpleNamespace(context=context), "profile", agent_runtimes=runtimes
        )
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

    control.context, control.bus, control.drain = context, bus, drain
    control.agent_stage = next(
        s for s in scheduler.stages if type(s).__name__ == "ProcessStage"
    ).agent_sub_stage.agent_sub_stage
    yield control
    dispatcher.cancel()
    pending = [dispatcher, *bus._pending_tasks]
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    await native.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["completed", "cancelled", "failed"])
@pytest.mark.parametrize("streaming", [False, True])
async def test_proactive_tool_delivery_is_saved_before_wakeup_finishes(
    runtime, outcome, streaming
):
    """Retain delivered text while the agent is still running and after it exits."""
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
    before_completion = (await runtime.store.read(runtime.cid)).messages
    if outcome == "cancelled":
        await runtime.bus.stop_platform("target")
    else:
        runtime.after_delivery.set()
        await asyncio.wait_for(runtime.drain(), 1)
    assert delivered in before_completion
    history = (await runtime.store.read(runtime.cid)).messages
    if outcome == "completed":
        assert history.count(delivered) == 1
        assert "Take your medicine" in json.dumps(history)
        assert any(message["role"] == "tool" for message in history)
    else:
        assert history.count(delivered) == 1


@pytest.mark.asyncio
async def test_reply_to_running_wakeup_waits_and_sees_delivered_text(runtime):
    """Serialize a quick user reply and preserve the actual reminder in its context."""
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
@pytest.mark.parametrize("completion", ["Take your medicine", ""])
async def test_tool_delivery_survives_duplicate_or_empty_final_reply(
    runtime, completion
):
    """Keep exactly one assistant record when the final reply adds no new text."""
    runtime.completion = completion
    await wake_main_agent(
        runtime.context,
        umo="target:FriendMessage:user",
        user_prompt="Send a reminder",
        source="background_task",
    )
    await asyncio.wait_for(runtime.drain(), 1)
    history = (await runtime.store.read(runtime.cid)).messages
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
@pytest.mark.parametrize("failure", ["missing_platform", "transport", "storage"])
async def test_proactive_delivery_distinguishes_send_and_storage_failures(
    runtime, failure, monkeypatch
):
    """Only confirmed text becomes assistant history; storage failure never resends."""
    if failure == "missing_platform":
        runtime.context.send_message.return_value = False
    elif failure == "transport":
        runtime.context.send_message.side_effect = RuntimeError("Transport unavailable")
    else:
        monkeypatch.setattr(
            ConversationEventWriter,
            "save_history",
            AsyncMock(side_effect=RuntimeError("Storage unavailable")),
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
    snapshot = await runtime.store.read(runtime.cid)
    assert {"role": "assistant", "content": "Take your medicine"} not in snapshot.messages


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["switched", "deleted"])
async def test_proactive_delivery_stays_bound_to_its_original_conversation(
    runtime, change
):
    """Never redirect a delivery to a newly selected or replacement conversation."""
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
    manager.session_conversations["target:FriendMessage:user"] = "another-conversation"
    if change == "deleted":
        await runtime.store.delete(cid=runtime.cid)
    runtime.gate.set()
    if change == "deleted":
        await asyncio.wait_for(runtime.drain(), 2)
        assert await runtime.store.read(runtime.cid) is None
    else:
        await asyncio.wait_for(runtime.delivered.wait(), 2)
        await runtime.bus.stop_platform("target")
        snapshot = await runtime.store.read(runtime.cid)
        assert {
            "role": "assistant",
            "content": "Take your medicine",
        } in snapshot.messages
    assert await runtime.store.read("another-conversation") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("temporary_scope", ["message", "part"])
@pytest.mark.parametrize("streaming", [False, True])
async def test_temporary_final_text_cannot_replace_a_confirmed_delivery(
    runtime, monkeypatch, temporary_scope, streaming
):
    """Only persisted final content may suppress the delivered assistant record."""
    runtime.completion = "Take your medicine"
    runtime.agent_stage.streaming_response = streaming

    async def mark_final_text_temporary(self, run_context, llm_response):
        final = run_context.messages[-1]
        if temporary_scope == "message":
            final._no_save = True
        else:
            for part in final.content:
                part.mark_as_temp()

    monkeypatch.setattr(BaseAgentRunHooks, "on_agent_done", mark_final_text_temporary)
    await wake_main_agent(
        runtime.context,
        umo="target:FriendMessage:user",
        user_prompt="Send a reminder",
        source="plugin",
    )
    await asyncio.wait_for(runtime.drain(), 1)
    snapshot = await runtime.store.read(runtime.cid)
    assert (
        snapshot.messages.count({"role": "assistant", "content": "Take your medicine"})
        == 1
    )


@pytest.mark.asyncio
async def test_platform_stop_waits_for_delivery_commit(runtime, monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()
    save_history = ConversationEventWriter.save_history

    async def blocked(writer, *args, **kwargs):
        entered.set()
        await release.wait()
        return await save_history(writer, *args, **kwargs)

    monkeypatch.setattr(ConversationEventWriter, "save_history", blocked)
    await wake_main_agent(
        runtime.context,
        umo="target:FriendMessage:user",
        user_prompt="Send a reminder",
        source="cron",
    )
    await asyncio.wait_for(entered.wait(), 2)
    stopping = asyncio.create_task(runtime.bus.stop_platform("target"))
    for _ in range(20):
        await asyncio.sleep(0)
    assert not stopping.done()
    release.set()
    await asyncio.wait_for(stopping, 2)
    snapshot = await runtime.store.read(runtime.cid)
    assert (
        snapshot.messages.count({"role": "assistant", "content": "Take your medicine"})
        == 1
    )


@pytest.mark.asyncio
async def test_dashboard_edit_is_not_overwritten_by_wakeup(runtime):
    runtime.after_delivery.clear()
    await wake_main_agent(
        runtime.context,
        umo="target:FriendMessage:user",
        user_prompt="Send a reminder",
        source="cron",
    )
    await asyncio.wait_for(runtime.delivered.wait(), 2)
    writer = ConversationEventWriter(
        runtime.store, await runtime.store.read(runtime.cid)
    )
    edited = [{"role": "assistant", "content": "Dashboard edit"}]
    await writer.save_history(edited, origin="user")
    runtime.after_delivery.set()
    await asyncio.wait_for(runtime.drain(), 2)
    assert (await runtime.store.read(runtime.cid)).messages == edited
