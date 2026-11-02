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
from astrbot.core.astr_agent_run_util import AgentRunner
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
from astrbot.core.utils import trace as trace_module


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
        deliver=False,
        fail=False,
    )
    control.gate.set()

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
            if control.deliver:
                await event.send(MessageChain().message("Explicit delivery"))
            return LLMResponse(
                role="err" if control.fail else "assistant",
                completion_text=f"Reply {len(control.requests)}",
            )
        finally:
            control.cleaned.set()

    async def respond_stream(**kwargs):
        response = await respond(**kwargs)
        if response.role != "err":
            for text in ("Reply ", str(len(control.requests))):
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
        runner = AgentRunner()
        await runner.reset(
            provider=provider,
            request=prepared.request,
            run_context=ContextWrapper(context=SimpleNamespace(event=event)),
            tool_executor=MagicMock(),
            agent_hooks=BaseAgentRunHooks(),
            streaming=config.streaming_response,
        )
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
