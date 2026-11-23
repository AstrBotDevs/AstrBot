"""Runtime ownership, history locking, and native SDK request-hook regressions."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.types import CallToolResult, TextContent

from astrbot.core.agent.input import PlainInput
from astrbot.core.agent.message import Message, load_messages
from astrbot.core.agent.output import PlainOutput
from astrbot.core.agent.response import AgentStats
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.tool_loop_agent_runner import (
    ToolLoopAgentRunner,
    _ToolExecutionInterrupted,
)
from astrbot.core.agent.runtime import AgentPermissions, TurnResult, TurnStatus
from astrbot.core.astr_agent_runtime import execution as native_execution
from astrbot.core.astr_agent_runtime import session as native_session
from astrbot.core.astr_agent_runtime.context import AstrAgentContext
from astrbot.core.astr_agent_runtime.main_agent import builder
from astrbot.core.astr_agent_runtime.main_agent.config import MainAgentBuildConfig
from astrbot.core.astr_agent_runtime.main_session import MainAgentInput
from astrbot.core.astr_agent_runtime.runtime import AstrAgentRuntime
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.provider.provider import Provider
from astrbot.core.star.context import Context


class ObservedSignal(asyncio.Event):
    """Record completion of the real stop/steering waiter coroutines."""

    def __init__(self):
        super().__init__()
        self.exited = asyncio.Event()

    async def wait(self):
        try:
            return await super().wait()
        finally:
            self.exited.set()


@pytest.mark.asyncio
@pytest.mark.parametrize("exit_mode", ["cancel", "close", "stop"])
async def test_tool_reader_and_stop_watchers_are_joined(exit_mode):
    before = set(asyncio.all_tasks())
    started, closed = asyncio.Event(), asyncio.Event()
    runner = ToolLoopAgentRunner()
    runner._abort_signal = ObservedSignal()
    runner._steering_signal = ObservedSignal()

    async def tool_results():
        try:
            started.set()
            if exit_mode == "close":
                yield "first"
            await asyncio.Event().wait()
            yield "unreachable"
        finally:
            await asyncio.sleep(0)
            closed.set()

    stream = runner._iter_tool_executor_results(tool_results(), detach=lambda **_: None)
    pending = asyncio.create_task(anext(stream))
    try:
        await asyncio.wait_for(started.wait(), 2)
        if exit_mode == "close":
            assert await asyncio.wait_for(pending, 2) == "first"
            await asyncio.wait_for(stream.aclose(), 2)
        elif exit_mode == "cancel":
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(pending, 2)
        else:
            runner.request_stop()
            with pytest.raises(_ToolExecutionInterrupted):
                await asyncio.wait_for(pending, 2)
        assert closed.is_set()
        assert runner._abort_signal.exited.is_set()
        assert runner._steering_signal.exited.is_set()
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        await stream.aclose()
    assert not (set(asyncio.all_tasks()) - before)


@pytest.mark.asyncio
@pytest.mark.parametrize("accepted", [True, False])
async def test_handoff_transfers_the_existing_reader_only_on_acceptance(accepted):
    before = set(asyncio.all_tasks())
    started, release, closed = asyncio.Event(), asyncio.Event(), asyncio.Event()
    calls, owners, handed_off = [], [], []
    runner = ToolLoopAgentRunner()
    runner._abort_signal = ObservedSignal()
    runner._steering_signal = ObservedSignal()
    receipt = CallToolResult(content=[TextContent(type="text", text="accepted")])
    result = CallToolResult(content=[TextContent(type="text", text="finished")])

    async def tool_results():
        calls.append("invoke")
        owners.append(asyncio.current_task())
        try:
            started.set()
            await release.wait()
            owners.append(asyncio.current_task())
            yield result
        finally:
            closed.set()

    def detach(*, executor, pending_result):
        handed_off.append((executor, pending_result))
        return receipt if accepted else None

    stream = runner._iter_tool_executor_results(tool_results(), detach=detach)
    foreground = asyncio.create_task(anext(stream))
    try:
        await asyncio.wait_for(started.wait(), 2)
        tasks_before_handoff = set(asyncio.all_tasks())
        runner._steering_signal.set()
        if accepted:
            assert await asyncio.wait_for(foreground, 2) is receipt
            await stream.aclose()
            assert len(handed_off) == 1
            executor, pending = handed_off[0]
            assert pending in tasks_before_handoff and pending is not foreground
            assert not pending.done() and not closed.is_set()
            assert runner._abort_signal.exited.is_set()
            assert runner._steering_signal.exited.is_set()
            release.set()
            assert await asyncio.wait_for(pending, 2) is result
            with pytest.raises(StopAsyncIteration):
                await asyncio.wait_for(anext(executor), 2)
            await executor.aclose()
        else:
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert not foreground.done()
            release.set()
            assert await asyncio.wait_for(foreground, 2) is result
            await stream.aclose()
            assert len(handed_off) == 1
        assert calls == ["invoke"]
        assert closed.is_set()
        assert owners[0] is owners[1]
    finally:
        release.set()
        foreground.cancel()
        await asyncio.gather(foreground, return_exceptions=True)
        await stream.aclose()
        if accepted and handed_off:
            executor, pending = handed_off[0]
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
            await executor.aclose()
    assert not (set(asyncio.all_tasks()) - before)


def make_event(umo):
    """Provide a mutable event boundary with real permission and message metadata."""
    extras = {}
    event = MagicMock(spec=AstrMessageEvent)
    event.unified_msg_origin = umo
    event.role = "member"
    event.message_obj = SimpleNamespace(message=[])
    event.platform_meta = PlatformMetadata(id="test", name="test", description="Test")
    event.plugins_name = None
    event.get_extra.side_effect = lambda key, default=None: extras.get(key, default)
    event.set_extra.side_effect = lambda key, value: extras.__setitem__(key, value)
    event.is_stopped.return_value = False
    event.get_message_type.return_value = MessageType.FRIEND_MESSAGE
    event.get_platform_name.return_value = "test"
    event.get_sender_id.return_value = "caller"
    event.trace = MagicMock()
    return event


@pytest.fixture
def history_runtime(monkeypatch):
    """Keep native sessions/history policy real; replace model and database I/O."""
    first_execution = asyncio.Event()
    first_commit = asyncio.Event()
    release_execution = asyncio.Event()
    release_commit = asyncio.Event()
    second_execution = asyncio.Event()
    records, histories, reads, admissions, builds = {}, {}, [], [], []
    provider = MagicMock(spec=Provider)
    provider.provider_config = {"id": "test-model"}
    provider.get_model.return_value = "test-model"
    provider.meta.return_value = SimpleNamespace(type="test")
    response = LLMResponse(role="assistant", completion_text="completed")

    async def metadata(cid):
        return records.get(cid)

    async def read_for_execution(cid):
        reads.append(cid)
        record = records[cid]
        return SimpleNamespace(**vars(record), content=deepcopy(histories[cid])), None

    async def commit(umo, cid, *, history, token_usage):
        assert records[cid].umo == umo
        if history[-1]["content"] == "reply:first":
            first_commit.set()
            await release_commit.wait()
        histories[cid] = deepcopy(history)

    manager = SimpleNamespace(
        db=SimpleNamespace(
            conversation_store=SimpleNamespace(
                get_metadata=AsyncMock(side_effect=metadata),
                read_for_execution=AsyncMock(side_effect=read_for_execution),
            )
        ),
        to_legacy_conversation=lambda record: record,
        update_conversation=AsyncMock(side_effect=commit),
    )
    host = MagicMock(spec=Context)
    host.conversation_manager = manager
    host.get_config.return_value = {}
    runtime = AstrAgentRuntime(
        host, agent_configs=SimpleNamespace(), subagents=SimpleNamespace()
    )

    async def collect(event, context, config, *, req, **kwargs):
        return req, None

    async def build(**kwargs):
        request = kwargs["req"]
        builds.append((request.prompt, deepcopy(request.contexts)))
        wrapper = ContextWrapper(
            context=AstrAgentContext(context=host, event=kwargs["event"])
        )
        wrapper.messages = load_messages(request.contexts) + [
            Message(role="user", content=request.prompt)
        ]
        runner = SimpleNamespace(
            run_context=wrapper,
            streaming=False,
            stats=AgentStats(),
            provider=provider,
            get_final_llm_resp=lambda: response,
            was_aborted=lambda: False,
            _resolve_unconsumed_follow_ups=lambda: None,
            request_stop=lambda: None,
        )
        return builder.MainAgentBuildResult(runner, request, provider)

    async def execute(runner, turn, max_steps):
        prompt = turn.input.request.prompt
        if prompt == "first":
            first_execution.set()
            await release_execution.wait()
        else:
            second_execution.set()
        runner.run_context.messages.append(
            Message(role="assistant", content=f"reply:{prompt}")
        )
        return TurnResult(content=(PlainOutput(text=f"reply:{prompt}"),))

    monkeypatch.setattr(
        "astrbot.core.astr_agent_runtime.main_session.collect_initial_request", collect
    )
    monkeypatch.setattr(builder, "build_main_agent", build)
    monkeypatch.setattr(native_session, "execute_native_loop", execute)
    monkeypatch.setattr(native_session, "record_agent_stats", AsyncMock())
    monkeypatch.setattr(native_session.Metric, "upload", AsyncMock())
    monkeypatch.setattr(
        "astrbot.core.astr_agent_runtime.computer.computer_client.shutdown_local_booter",
        AsyncMock(),
    )
    return SimpleNamespace(
        runtime=runtime,
        records=records,
        histories=histories,
        reads=reads,
        admissions=admissions,
        builds=builds,
        first_execution=first_execution,
        first_commit=first_commit,
        release_execution=release_execution,
        release_commit=release_commit,
        second_execution=second_execution,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["same_session", "same_origin", "different_origins"])
async def test_native_session_history_locks_admission_through_commit(
    history_runtime, scope
):
    env = history_runtime
    first_umo = "test:FriendMessage:alice"
    second_umo = "test:FriendMessage:bob" if scope == "different_origins" else first_umo
    second_cid = "first" if scope == "same_session" else "second"
    for cid, umo in [("first", first_umo), (second_cid, second_umo)]:
        env.records[cid] = SimpleNamespace(
            cid=cid,
            conversation_id=cid,
            umo=umo,
            user_id=umo,
            revision=0,
            token_usage=0,
        )
        env.histories[cid] = [{"role": "user", "content": f"seed:{cid}"}]

    async def open_turn(cid, umo, prompt):
        session = await env.runtime.open_session(
            umo, session_id=cid, options={"profile": "main"}
        )
        request = ProviderRequest(prompt=prompt, conversation=env.records[cid])
        input = MainAgentInput(
            event=make_event(umo),
            permissions=AgentPermissions(),
            content=[PlainInput(text=prompt)],
            request=request,
            build_config=MainAgentBuildConfig(
                tool_call_timeout=10, call_request_hook=False
            ),
        )

        async def admit():
            env.admissions.append(prompt)
            return True

        return session, await session.run_turn(input, admit=admit)

    try:
        first_session, first = await open_turn("first", first_umo, "first")
        await asyncio.wait_for(env.first_execution.wait(), 2)
        second_session, second = await open_turn(second_cid, second_umo, "second")
        assert (first_session is second_session) is (scope == "same_session")
        if scope == "different_origins":
            await asyncio.wait_for(env.second_execution.wait(), 2)
            assert (
                await asyncio.wait_for(second.result(), 2)
            ).status == TurnStatus.COMPLETED
            assert not first.done
            assert env.builds[1][1] == [{"role": "user", "content": "seed:second"}]
        else:
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert env.admissions == ["first"]
            assert env.reads == ["first"]
            assert not env.second_execution.is_set()

        env.release_execution.set()
        await asyncio.wait_for(env.first_commit.wait(), 2)
        if scope != "different_origins":
            assert env.admissions == ["first"]
            assert env.reads == ["first"]
            assert not second.done
        env.release_commit.set()
        assert (
            await asyncio.wait_for(first.result(), 2)
        ).status == TurnStatus.COMPLETED
        assert (
            await asyncio.wait_for(second.result(), 2)
        ).status == TurnStatus.COMPLETED
        second_history = next(
            history for prompt, history in env.builds if prompt == "second"
        )
        if scope == "same_session":
            assert second_history[-2:] == [
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "reply:first"},
            ]
            assert env.histories["first"][-1] == {
                "role": "assistant",
                "content": "reply:second",
            }
        else:
            assert second_history == [{"role": "user", "content": "seed:second"}]
            assert env.histories["first"][-1] == {
                "role": "assistant",
                "content": "reply:first",
            }
            assert env.histories["second"][-1] == {
                "role": "assistant",
                "content": "reply:second",
            }
        assert env.runtime._active_main == {}
    finally:
        env.release_execution.set()
        env.release_commit.set()
        await asyncio.wait_for(env.runtime.close(), 2)
    await asyncio.sleep(0)


@pytest.fixture
def request_bridge(monkeypatch):
    """Exercise the actual builder while stubbing unrelated preparation boundaries."""
    event = make_event("test:FriendMessage:bridge")
    request = ProviderRequest(prompt="original")
    provider = MagicMock(spec=Provider)
    provider.provider_config = {
        "id": "selected-provider",
        "modalities": ["image", "tool_use"],
    }
    provider.get_model.return_value = "test"
    bridge = SimpleNamespace(dispatch_message_event=AsyncMock())
    host = MagicMock(spec=Context)
    host.conversation_manager = object()
    host.sdk_plugin_bridge = bridge
    prepared = SimpleNamespace(
        request=request, image_max_size=1280, images={}, captioned_refs=set()
    )
    monkeypatch.setattr(
        builder.request, "prepare_request", AsyncMock(return_value=prepared)
    )
    monkeypatch.setattr(builder.persona, "apply_persona", AsyncMock())
    monkeypatch.setattr(builder.workspace, "apply_workspace_instructions", AsyncMock())
    monkeypatch.setattr(builder.knowledge_base, "apply_knowledge_base", AsyncMock())
    monkeypatch.setattr(builder.computer_use, "apply_computer_use", AsyncMock())
    monkeypatch.setattr(
        builder.subagent, "apply_subagents", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(builder.web_search, "apply_web_search", lambda *_: "")
    monkeypatch.setattr(builder.providers, "resolve_fallback_providers", lambda *_: [])
    monkeypatch.setattr(
        builder.providers, "select_image_provider", lambda selected, *_: selected
    )
    images = AsyncMock()
    classic = AsyncMock(return_value=False)
    runner = object()
    create_runner = AsyncMock(return_value=runner)
    monkeypatch.setattr(builder, "prepare_request_images", images)
    monkeypatch.setattr(builder, "call_event_hook", classic)
    monkeypatch.setattr(native_execution, "create_native_runner", create_runner)

    async def build(*, hooks=True):
        return await builder.build_main_agent(
            event=event,
            plugin_context=host,
            provider=provider,
            req=request,
            config=MainAgentBuildConfig(
                tool_call_timeout=10,
                call_request_hook=hooks,
                enable_message_delivery=False,
                add_cron_tools=False,
                validate_provider_endpoint=False,
            ),
        )

    return SimpleNamespace(
        event=event,
        request=request,
        provider=provider,
        bridge=bridge,
        host=host,
        classic=classic,
        images=images,
        create_runner=create_runner,
        runner=runner,
        build=build,
    )


@pytest.mark.asyncio
async def test_sdk_llm_request_follows_classic_hook_and_preserves_mutable_request(
    request_bridge,
):
    env = request_bridge
    order = []

    async def classic(event, event_type, request, **kwargs):
        assert request is env.request
        request.prompt = "classic"
        order.append("classic")
        return False

    async def sdk(name, event, payload, *, provider_request):
        assert name == "llm_request" and event is env.event
        assert payload == {
            "prompt": "classic",
            "provider_id": "selected-provider",
            "runner_type": "astrbot",
        }
        assert provider_request is env.request
        order.append("sdk")
        provider_request.prompt = "sdk"

    env.classic.side_effect = classic
    env.bridge.dispatch_message_event.side_effect = sdk
    result = await env.build()
    assert order == ["classic", "sdk"]
    assert (
        result.provider_request is env.request
        and result.provider_request.prompt == "sdk"
    )
    assert result.agent_runner is env.runner
    assert env.create_runner.await_args.args[2] is env.request
    assert env.images.await_count == 2


@pytest.mark.asyncio
async def test_sdk_llm_request_is_disabled_with_classic_request_hook(request_bridge):
    env = request_bridge
    assert await env.build(hooks=False) is not None
    env.classic.assert_not_awaited()
    env.bridge.dispatch_message_event.assert_not_awaited()
    env.create_runner.assert_awaited_once()
    assert env.images.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_at", ["classic", "sdk"])
async def test_request_hook_stop_prevents_runner_creation(request_bridge, stop_at):
    env = request_bridge
    if stop_at == "classic":
        env.classic.return_value = True
    else:
        env.bridge.dispatch_message_event.side_effect = lambda *_args, **_kwargs: (
            setattr(env.event.is_stopped, "return_value", True)
        )
    assert await env.build() is None
    env.create_runner.assert_not_awaited()
    assert env.images.await_count == 1
    assert env.bridge.dispatch_message_event.await_count == (
        0 if stop_at == "classic" else 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [RuntimeError("sdk failed"), asyncio.CancelledError()]
)
async def test_sdk_failure_settles_history_observer_and_preserves_cancellation(
    request_bridge, failure
):
    env = request_bridge
    writer = SimpleNamespace(closed=False, stage_history=MagicMock())
    env.host.conversation_manager = MagicMock(spec=ConversationManager)
    env.host.conversation_manager.create_event_writer = AsyncMock(return_value=writer)
    env.request.conversation = SimpleNamespace(cid="conversation", revision=7)
    env.bridge.dispatch_message_event.side_effect = failure
    if isinstance(failure, asyncio.CancelledError):
        with pytest.raises(asyncio.CancelledError):
            await env.build()
        env.create_runner.assert_not_awaited()
        assert env.images.await_count == 1
    else:
        assert await env.build() is not None
        env.create_runner.assert_awaited_once()
        assert env.images.await_count == 2
    assert [call.kwargs["origin"] for call in writer.stage_history.call_args_list] == [
        "unknown",
        "plugin",
    ]


@pytest.mark.asyncio
async def test_absent_sdk_bridge_keeps_native_request_working(request_bridge):
    env = request_bridge
    del env.host.sdk_plugin_bridge
    assert (await env.build()).provider_request is env.request
    env.bridge.dispatch_message_event.assert_not_awaited()
    env.create_runner.assert_awaited_once()
