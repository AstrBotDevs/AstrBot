"""Programmatic turns through the event bus and the real shared execution driver."""

import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from astrbot.core.agent.message import Message
from astrbot.core.agent.response import AgentResponse, AgentStats
from astrbot.core.agent.runners.base import AgentState
from astrbot.core.agent.runners.tool_loop_agent_runner import FollowUpTicket
from astrbot.core.astr_agent_wakeup import wake_main_agent
from astrbot.core.astr_main_agent import MainAgentBuildResult
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.event_bus import EventBus
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.pipeline.context import PipelineContext
from astrbot.core.pipeline.process_stage.method.agent_sub_stages import internal
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.utils.active_event_registry import active_event_registry
from astrbot.core.utils.session_lock import session_lock_manager


class ProbeRunner:
    """Produce UI frames while allowing tests to control execution and cancellation."""

    def __init__(self, event, request, control, provider):
        self.event = event
        self.req = request
        self.control = control
        self.provider = provider
        self.stats = AgentStats()
        self.streaming = control.config["provider_settings"]["streaming_response"]
        self.state = AgentState.RUNNING
        self.tickets = []
        self.run_context = SimpleNamespace(
            context=SimpleNamespace(event=event),
            messages=[
                *[Message.model_validate(m) for m in request.contexts],
                Message(role="user", content=request.prompt),
            ],
        )

    async def step(self):
        """Emit representative runner frames or a controlled execution failure.

        Yields:
            Tool status, provider statistics, streaming text, and final text.
        """
        self.control.started.set()
        self.control.active += 1
        self.control.max_active = max(self.control.max_active, self.control.active)
        try:
            await self.control.release.wait()
            if self.control.consume:
                for ticket in self.tickets:
                    self.run_context.messages.append(
                        Message(role="user", content=ticket.text)
                    )
                    ticket.consumed = True
                    ticket.resolved.set()
            if self.control.failure == "exception":
                raise RuntimeError("controlled execution failure")
            if self.control.deliver:
                await self.event.send(MessageChain().message("Explicit delivery"))
            for kind in (
                "tool_call",
                "tool_call_result",
                "agent_stats",
                "streaming_delta",
                "llm_result",
            ):
                yield AgentResponse(
                    type=kind,
                    data={"chain": MessageChain().message("Automatic output")},
                )
            self.run_context.messages.append(
                Message(role="assistant", content="Final result")
            )
            self.state = (
                AgentState.ERROR if self.control.failure == "state" else AgentState.DONE
            )
        finally:
            for ticket in self.tickets:
                ticket.resolved.set()
            self.control.active -= 1
            self.control.cleaned.set()

    def follow_up(self, *, message_text):
        if self.done():
            return None
        ticket = FollowUpTicket(seq=len(self.tickets), text=message_text)
        self.tickets.append(ticket)
        self.control.captured.set()
        return ticket

    def done(self):
        """Return whether the controlled run has finished.

        Returns:
            Whether a terminal state was reached.
        """
        return self.state in (AgentState.DONE, AgentState.ERROR)

    def get_final_llm_resp(self):
        """Return the final response associated with the controlled state.

        Returns:
            Final assistant or error response.
        """
        return LLMResponse(
            role="err" if self.state == AgentState.ERROR else "assistant",
            completion_text="Final result",
        )

    def request_stop(self):
        """Release execution when the event's cancellation callback fires."""
        self.control.release.set()

    def _resolve_unconsumed_follow_ups(self):
        pass

    def was_aborted(self):
        """Report whether partial interactive output needs saving.

        Returns:
            False because this probe produces no partial interactive turn.
        """
        return False


@pytest_asyncio.fixture
async def runtime(monkeypatch):
    """Create a real bus, scheduler, execution stage, and history writer.

    Args:
        monkeypatch: Pytest patch manager.

    Yields:
        Runtime controls and captured execution state.
    """
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["platform_settings"]["unique_session"] = True
    config["plugin_set"] = ["allowed"]
    history = [{"role": "user", "content": "Original"}]
    conversation = SimpleNamespace(cid="conversation", history=json.dumps(history))
    queue = asyncio.Queue()
    metadata = PlatformMetadata(id="target", name="aiocqhttp", description="Target")
    manager = SimpleNamespace(update_conversation=AsyncMock())

    async def save(*args, **kwargs):
        conversation.history = json.dumps(kwargs["history"])

    manager.update_conversation.side_effect = save
    context = SimpleNamespace(
        get_event_queue=lambda: queue,
        get_platform_inst=lambda _: SimpleNamespace(meta=lambda: metadata),
        get_config=lambda **_: config,
        conversation_manager=manager,
        get_using_tts_provider_async=AsyncMock(return_value=None),
        send_message=AsyncMock(return_value=True),
    )
    control = SimpleNamespace(
        context=context,
        config=config,
        history=history,
        conversation=conversation,
        started=asyncio.Event(),
        release=asyncio.Event(),
        cleaned=asyncio.Event(),
        failure=None,
        deliver=False,
        events=[],
        snapshots=[],
        errors=[],
        consume=False,
        captured=asyncio.Event(),
        active=0,
        max_active=0,
    )
    control.release.set()
    provider = SimpleNamespace(
        provider_config={"id": "provider"},
        get_model=lambda: "model",
        meta=lambda: SimpleNamespace(type="test"),
    )

    async def build(*, event, config, req=None, **kwargs):
        assert req is None
        req = ProviderRequest(prompt=event.message_str)
        assert event.plugins_name == ["allowed"]
        req.conversation = conversation
        req.contexts = json.loads(conversation.history)
        control.events.append(event)
        control.snapshots.append(json.loads(conversation.history))
        runner = ProbeRunner(event, req, control, provider)
        return MainAgentBuildResult(runner, req, provider)

    monkeypatch.setattr(internal, "build_main_agent", build)
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
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
    monkeypatch.setattr(internal.Metric, "upload", AsyncMock())
    monkeypatch.setattr(internal, "_record_internal_agent_stats", AsyncMock())
    pipeline_context = PipelineContext(
        config, SimpleNamespace(context=context), "profile"
    )
    scheduler = PipelineScheduler(pipeline_context)
    await scheduler.initialize()

    async def execute(event):
        try:
            await PipelineScheduler.execute(scheduler, event)
        except BaseException as error:
            control.errors.append(error)
            raise

    scheduler.execute = execute
    config_manager = MagicMock()
    config_manager.get_conf_info.return_value = {"id": "profile"}
    bus = EventBus(queue, {"profile": scheduler}, config_manager)
    dispatcher = asyncio.create_task(bus.dispatch())
    control.bus = bus
    control.dispatcher = dispatcher
    control.scheduler = scheduler

    async def drain():
        while not queue.empty() or bus._pending_tasks:
            await asyncio.sleep(0)
            pending = list(bus._pending_tasks)
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

    control.drain = drain
    yield control
    dispatcher.cancel()
    pending = [dispatcher, *bus._pending_tasks]
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("deliver", [False, True])
async def test_wakeup_keeps_umo_and_only_delivers_explicit_messages(
    runtime, streaming, deliver
):
    """Execute through the common driver without emitting automatic UI frames.

    Args:
        runtime: Real bus and pipeline runtime.
        streaming: Session streaming setting.
        deliver: Whether the tool explicitly delivers a message.
    """
    runtime.config["provider_settings"]["streaming_response"] = streaming
    runtime.deliver = deliver
    umo = "target:GroupMessage:user_group"
    await asyncio.wait_for(
        wake_main_agent(
            runtime.context, umo=umo, user_prompt="Current turn", source="plugin"
        ),
        1,
    )
    await asyncio.wait_for(runtime.drain(), 1)
    event = runtime.events[0]
    assert event.unified_msg_origin == umo
    assert event.get_result() is None
    assert event._has_send_oper is deliver
    assert runtime.context.send_message.await_count == int(deliver)
    saved = json.loads(runtime.conversation.history)
    assert saved == runtime.history + [
        {"role": "user", "content": "Current turn"},
        {"role": "assistant", "content": "Final result"},
    ]
    assert not runtime.bus._pending_tasks
    assert umo not in active_event_registry._events


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["exception", "state"])
async def test_wakeup_records_execution_failure_without_sending_it(runtime, failure):
    """Record pipeline errors separately from submission and preserve stored history.

    Args:
        runtime: Real bus and pipeline runtime.
        failure: Exception or terminal error state.
    """
    runtime.failure = failure
    await wake_main_agent(
        runtime.context,
        umo="target:FriendMessage:user",
        user_prompt="Run",
        source="cron",
    )
    await asyncio.wait_for(runtime.drain(), 1)
    assert len(runtime.errors) == 1
    assert isinstance(runtime.errors[0], RuntimeError)
    runtime.context.send_message.assert_not_awaited()
    runtime.context.conversation_manager.update_conversation.assert_not_awaited()


@pytest.mark.asyncio
async def test_wakeup_returns_before_execution_and_platform_stop_cancels_run(runtime):
    """Submit without waiting, while preserving normal platform cancellation."""
    runtime.release.clear()
    await asyncio.wait_for(
        wake_main_agent(
            runtime.context,
            umo="target:FriendMessage:user",
            user_prompt="Run",
            source="cron",
        ),
        1,
    )
    await asyncio.wait_for(runtime.started.wait(), 1)
    assert not runtime.cleaned.is_set()
    await runtime.bus.stop_platform("target")
    assert runtime.cleaned.is_set()
    assert not runtime.bus._pending_tasks
    assert "target:FriendMessage:user" not in active_event_registry._events
    runtime.context.conversation_manager.update_conversation.assert_not_awaited()


@pytest.mark.asyncio
async def test_wakeup_reads_history_after_the_existing_turn(runtime):
    """Acquire the shared lock before reading the latest conversation."""
    umo = "target:FriendMessage:user"
    async with session_lock_manager.acquire_lock(umo):
        await wake_main_agent(
            runtime.context, umo=umo, user_prompt="Run", source="cron"
        )
        for _ in range(20):
            if umo in active_event_registry._events:
                break
            await asyncio.sleep(0)
        assert umo in active_event_registry._events
        assert not runtime.events
        runtime.conversation.history = json.dumps(
            runtime.history
            + [
                {"role": "assistant", "content": "Foreground finished"},
            ]
        )
    await asyncio.wait_for(runtime.drain(), 1)
    assert runtime.snapshots[0][-1]["content"] == "Foreground finished"


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_platform", [False, True])
async def test_stopped_wakeup_never_starts_the_agent(runtime, stop_platform):
    """Respect adapter removal and a background tree stopped before execution."""
    runtime.dispatcher.cancel()
    await asyncio.gather(runtime.dispatcher, return_exceptions=True)
    signal = asyncio.Event()
    await wake_main_agent(
        runtime.context,
        umo="target:FriendMessage:user",
        user_prompt="Run",
        source="background_task",
        stop_signal=signal,
    )
    assert runtime.bus.event_queue.qsize() == 1
    if stop_platform:
        await runtime.bus.stop_platform("target")
        assert runtime.bus.event_queue.empty()
    else:
        signal.set()
        runtime.dispatcher = asyncio.create_task(runtime.bus.dispatch())
        await asyncio.wait_for(runtime.drain(), 1)
    assert not runtime.events


@pytest.mark.asyncio
@pytest.mark.parametrize("consume", [False, True])
@pytest.mark.parametrize("first_kind", ["message", "wakeup"])
async def test_same_conversation_merges_at_safe_boundary_or_runs_next(
    runtime,
    consume,
    first_kind,
):
    """Serialize all inputs using the conversation saved by the previous run."""
    umo = "target:FriendMessage:user"
    runtime.release.clear()
    runtime.consume = consume
    if first_kind == "message":
        message = AstrBotMessage()
        message.type = MessageType.FRIEND_MESSAGE
        message.self_id = "bot"
        message.sender = MessageMember(user_id="alice", nickname="Alice")
        message.message = []
        first = AstrMessageEvent(
            "First input",
            message,
            PlatformMetadata(id="target", name="aiocqhttp", description="Target"),
            "user",
        )
        await runtime.context.get_event_queue().put(first)
    else:
        await wake_main_agent(
            runtime.context,
            umo=umo,
            user_prompt="First input",
            source="plugin",
        )
    await asyncio.wait_for(runtime.started.wait(), 1)
    await wake_main_agent(
        runtime.context,
        umo=umo,
        user_prompt="New information",
        source="cron",
    )
    if first_kind == "wakeup":
        await asyncio.wait_for(runtime.captured.wait(), 1)
    else:
        for _ in range(20):
            if len(active_event_registry._events.get(umo, ())) == 2:
                break
            await asyncio.sleep(0)
        assert len(active_event_registry._events[umo]) == 2
        assert not runtime.captured.is_set()
    assert len(runtime.events) == 1
    runtime.release.set()
    await asyncio.wait_for(runtime.drain(), 1)
    merged = consume and first_kind == "wakeup"
    assert runtime.max_active == 1
    assert len(runtime.events) == (1 if merged else 2)
    history = json.loads(runtime.conversation.history)
    assert history[: len(runtime.history)] == runtime.history
    assert sum("New information" in str(m["content"]) for m in history) == 1
    if not merged:
        assert runtime.snapshots[1][-1] == {
            "role": "assistant",
            "content": "Final result",
        }
    assert not runtime.errors


@pytest.mark.asyncio
@pytest.mark.parametrize("gate", ["whitelist", "session", "rate", "safety"])
async def test_wakeup_runs_normal_access_and_safety_stages(runtime, gate):
    """Keep the ordinary pipeline's admission checks for triggered inputs."""
    names = {
        "whitelist": "WhitelistCheckStage",
        "session": "SessionStatusCheckStage",
        "rate": "RateLimitStage",
        "safety": "ContentSafetyCheckStage",
    }
    stage = next(s for s in runtime.scheduler.stages if type(s).__name__ == names[gate])
    invoked = []

    async def reject(event):
        invoked.append(event)
        event.stop_event()

    stage.process = reject
    await wake_main_agent(
        runtime.context,
        umo="target:FriendMessage:user",
        user_prompt="Run",
        source="cron",
    )
    await asyncio.wait_for(runtime.drain(), 1)
    assert len(invoked) == 1
    assert not runtime.events


@pytest.mark.asyncio
async def test_unconsumed_input_is_released_when_the_active_run_fails(runtime):
    """An exception releases pending follow-up tickets and the conversation lock."""
    runtime.release.clear()
    runtime.failure = "exception"
    for prompt in ("First input", "Second input"):
        await wake_main_agent(
            runtime.context,
            umo="target:FriendMessage:user",
            user_prompt=prompt,
            source="plugin",
        )
        if prompt == "First input":
            await asyncio.wait_for(runtime.started.wait(), 1)
    await asyncio.wait_for(runtime.captured.wait(), 1)
    runtime.release.set()
    await asyncio.wait_for(runtime.drain(), 1)
    assert len(runtime.events) == 2
    assert len(runtime.errors) == 2
    assert runtime.max_active == 1


@pytest.mark.asyncio
async def test_wakeup_passes_the_shared_stage_with_a_provider_prefix(runtime):
    """Programmatic input is already admitted before provider prefix collection."""
    process_stage = next(
        stage
        for stage in runtime.scheduler.stages
        if type(stage).__name__ == "ProcessStage"
    )
    process_stage.agent_sub_stage.prov_wake_prefix = "/llm "
    await wake_main_agent(
        runtime.context,
        umo="target:FriendMessage:user",
        user_prompt="Continue",
        source="cron",
    )
    await asyncio.wait_for(runtime.drain(), 1)
    assert len(runtime.events) == 1
    assert not runtime.errors
