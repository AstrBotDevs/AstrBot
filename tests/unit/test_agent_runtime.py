"""Behavioral contract for runtime turns, independent of native model execution."""

import asyncio
import gc
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.input import PlainInput
from astrbot.core.agent.output import PlainOutput
from astrbot.core.agent.runtime import (
    AgentInput,
    AgentPermissions,
    AgentRole,
    AgentSession,
    InputReceipt,
    SessionState,
    TurnResult,
    TurnStatus,
    get_agent_permissions,
)


class RecordingSession(AgentSession):
    def __init__(self):
        super().__init__("conversation", "test:FriendMessage:alice")
        self.entered = asyncio.Queue()
        self.release = asyncio.Event()
        self.saved = []

    async def execute_turn(self, turn):
        await self.entered.put(turn)
        await self.release.wait()
        self.saved.append(turn.id)
        assert turn.input.content is not None
        return TurnResult(content=(PlainOutput(text=turn.input.content[0].text),))

    async def history(self):
        return list(self.saved)


def make_input(text="hello", *, sender="alice", role=AgentRole.MEMBER):
    event = SimpleNamespace(
        unified_msg_origin="test:FriendMessage:alice",
        get_sender_id=lambda: sender,
        plugins_name=None,
    )
    return AgentInput(event, AgentPermissions(role), [PlainInput(text=text)])


@pytest.mark.asyncio
async def test_queued_cancellation_does_not_release_an_earlier_turn():
    session = RecordingSession()
    assert session.state == SessionState.IDLE
    first = await session.run_turn(make_input("first"))
    assert session.state == SessionState.QUEUED
    assert session.pending_turn_count == 1
    await session.entered.get()
    assert session.state == SessionState.RUNNING
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(first.result(), 0.01)
    assert not first.done
    second = await first.follow_up(make_input("second"))
    third = await first.follow_up(make_input("third"))
    assert session.pending_turn_count == 2
    await second.cancel()
    await asyncio.sleep(0)
    assert session.entered.empty()
    session.release.set()
    assert (await first.result()).text == "first"
    assert (await third.result()).text == "third"
    assert (await second.result()).status == TurnStatus.CANCELLED
    assert session.saved == [first.id, third.id]
    assert session.state == SessionState.IDLE
    await session.close()
    assert session.state == SessionState.CLOSED


@pytest.mark.asyncio
async def test_close_cancels_active_and_queued_turns_without_deleting_history():
    session = RecordingSession()
    first = await session.run_turn(make_input())
    await session.entered.get()
    second = await first.follow_up(make_input())
    await session.close()
    assert (await first.result()).status == TurnStatus.CANCELLED
    assert (await second.result()).status == TurnStatus.CANCELLED
    assert not session.saved
    with pytest.raises(ValueError, match="closed"):
        await session.run_turn(make_input())


@pytest.mark.asyncio
async def test_steering_allows_other_senders_within_session_permissions():
    session = RecordingSession()
    turn = await session.run_turn(make_input())
    await session.entered.get()
    session.steer_turn = lambda target, input: (
        asyncio.get_running_loop().create_future()
    )
    assert turn.steer(make_input(role=AgentRole.ADMIN)) is None
    other_session = make_input(sender="bob")
    other_session.event.unified_msg_origin = "test:GroupMessage:other"
    assert turn.steer(other_session) is None
    other_plugins = make_input(sender="bob")
    other_plugins.event.plugins_name = ["other_plugin"]
    assert turn.steer(other_plugins) is None
    receipt = turn.steer(make_input(sender="bob"))
    assert receipt is not None
    receipt.set_result(False)
    session.release.set()
    await turn.result()
    assert turn.steer(make_input()) is None
    await session.close()


def test_permissions_respect_api_key_administrator_ceiling():
    event = SimpleNamespace(role="admin", get_extra=lambda key: False)
    assert not AgentPermissions.from_event(event).is_admin
    event.get_extra = lambda key: None
    assert AgentPermissions.from_event(event).is_admin


@pytest.mark.asyncio
async def test_cancelled_receipt_waiter_cannot_lose_a_committed_input():
    receipt = InputReceipt()

    async def wait():
        return await receipt

    waiter = asyncio.create_task(wait())
    await asyncio.sleep(0)
    waiter.cancel()
    await asyncio.gather(waiter, return_exceptions=True)
    assert not receipt.done()
    receipt.resolve(True)
    assert await receipt


def test_explicit_permissions_override_mutable_event_role():
    context = SimpleNamespace(
        context=SimpleNamespace(
            permissions=AgentPermissions(AgentRole.MEMBER),
            event=SimpleNamespace(role="admin", get_extra=lambda _: None),
        )
    )
    assert not get_agent_permissions(context).is_admin


@pytest.mark.asyncio
async def test_repeated_close_waits_for_cleanup_without_cancelling_it_twice():
    session = RecordingSession()
    cleaning, release_cleanup = asyncio.Event(), asyncio.Event()

    async def execute(turn):
        await session.entered.put(turn)
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release_cleanup.wait()

    session.execute_turn = execute
    turn = await session.run_turn(make_input())
    await session.entered.get()
    first_close = asyncio.create_task(session.close())
    await asyncio.wait_for(cleaning.wait(), 1)
    second_close = asyncio.create_task(session.close())
    await asyncio.sleep(0)
    assert not first_close.done() and not second_close.done()
    release_cleanup.set()
    await asyncio.wait_for(asyncio.gather(first_close, second_close), 1)
    assert (await turn.result()).status == TurnStatus.CANCELLED


class _DummyTurn:
    done = False

    async def cancel(self) -> None:
        return None


def _make_astr_runtime(*, max_idle_sessions: int = 2):
    from astrbot.core.astr_agent_runtime.runtime import AstrAgentRuntime

    conversations: dict[str, SimpleNamespace] = {}

    class FakeStore:
        async def get_metadata(self, cid: str):
            return conversations.get(cid)

    conv_mgr = MagicMock()
    conv_mgr.db = SimpleNamespace(conversation_store=FakeStore())
    conv_mgr.register_on_session_deleted = MagicMock()
    conv_mgr.register_on_conversation_deleted = MagicMock()
    subagents = MagicMock()
    subagents.store = SimpleNamespace(find_native_conversation=lambda umo, cid: None)
    subagents.evict_umo = MagicMock()
    subagents.evict_scope = MagicMock()
    context = SimpleNamespace(
        conversation_manager=conv_mgr,
        astrbot_config_mgr=SimpleNamespace(confs={}),
    )
    runtime = AstrAgentRuntime(
        context,
        agent_configs=MagicMock(),
        subagents=subagents,
        max_idle_sessions=max_idle_sessions,
    )
    return runtime, conversations, conv_mgr, subagents


@pytest.mark.asyncio
async def test_astr_runtime_lru_eviction_preserves_live_handles_without_closing():
    """LRU cache eviction pops handles without closing retained caller references."""
    runtime, conversations, _, _ = _make_astr_runtime(max_idle_sessions=2)
    for cid in ("c1", "c2", "c3", "c4"):
        conversations[cid] = SimpleNamespace(umo=f"p:FriendMessage:{cid}")

    s1 = await runtime.open_session("p:FriendMessage:c1", session_id="c1")
    s2 = await runtime.open_session("p:FriendMessage:c2", session_id="c2")

    active_turn = _DummyTurn()
    s1._turns.add(active_turn)
    s1.active_turn = active_turn

    s3 = await runtime.open_session("p:FriendMessage:c3", session_id="c3")
    assert ("main", "c1") in runtime._sessions
    assert ("main", "c2") not in runtime._sessions
    # LRU eviction does not close retained handles so callers/follow-ups stay valid.
    assert s2.closed is False
    assert ("main", "c3") in runtime._sessions

    # While caller holds s2, re-opening reuses the exact live instance.
    s2_reopened = await runtime.open_session("p:FriendMessage:c2", session_id="c2")
    assert s2_reopened is s2
    assert ("main", "c3") not in runtime._sessions
    assert s3.closed is False

    # Settling s1 trims over-capacity idle entries via on_session_idle.
    s1._turns.clear()
    s1.active_turn = None
    s1._on_turn_settled()
    assert len(runtime._sessions) <= 2

    # Dropping strong references lets WeakValueDictionary release c3.
    del s3
    gc.collect()
    s3_fresh = await runtime.open_session("p:FriendMessage:c3", session_id="c3")
    assert s3_fresh.closed is False

    await runtime.close()


@pytest.mark.asyncio
async def test_astr_runtime_deletion_callbacks_and_deferred_active_close():
    """Explicit deletion closes idle sessions immediately and active ones once settled."""
    runtime, conversations, conv_mgr, subagents = _make_astr_runtime(
        max_idle_sessions=8
    )
    conversations["c1"] = SimpleNamespace(umo="p:FriendMessage:u1")
    conversations["c2"] = SimpleNamespace(umo="p:FriendMessage:u1")
    conversations["c3"] = SimpleNamespace(umo="p:FriendMessage:u2")

    await runtime.initialize()
    conv_mgr.register_on_session_deleted.assert_called_once_with(runtime.evict_umo)
    conv_mgr.register_on_conversation_deleted.assert_called_once_with(
        runtime.evict_conversation
    )

    s1 = await runtime.open_session("p:FriendMessage:u1", session_id="c1")
    s2 = await runtime.open_session("p:FriendMessage:u1", session_id="c2")
    s3 = await runtime.open_session("p:FriendMessage:u2", session_id="c3")

    active_turn = _DummyTurn()
    s1._turns.add(active_turn)
    s1.active_turn = active_turn

    await runtime.evict_umo("p:FriendMessage:u1")
    assert ("main", "c1") not in runtime._sessions
    assert ("main", "c2") not in runtime._sessions
    assert s2.closed is True
    assert s1.closed is False
    subagents.evict_umo.assert_called_once_with("p:FriendMessage:u1")

    # Once active turn settles, _on_turn_settled schedules deferred close.
    s1._turns.clear()
    s1.active_turn = None
    s1._on_turn_settled()
    await asyncio.sleep(0)
    await asyncio.gather(*list(runtime._deferred_close_tasks), return_exceptions=True)
    assert s1.closed is True

    # Single-conversation deletion closes its session and evicts subagent scope.
    await runtime.evict_conversation("p:FriendMessage:u2", "c3")
    assert s3.closed is True
    subagents.evict_scope.assert_called_once_with("p:FriendMessage:u2", "c3")
    await runtime.close()


@pytest.mark.asyncio
async def test_astr_runtime_close_sessions_logs_errors(caplog):
    """_close_sessions logs close failures instead of silently swallowing them."""
    runtime, _, _, _ = _make_astr_runtime()
    bad_session = SimpleNamespace(
        id="bad-sess",
        close=AsyncMock(side_effect=RuntimeError("boom")),
    )
    await runtime._close_sessions([bad_session])
    assert "Failed to close evicted session bad-sess: boom" in caplog.text


@pytest.mark.asyncio
async def test_conversation_manager_delete_conversation_triggers_callback(monkeypatch):
    """delete_conversation notifies registered conversation-deletion listeners."""
    from astrbot.core import sp
    from astrbot.core.conversation_mgr import ConversationManager

    mgr = ConversationManager.__new__(ConversationManager)
    mgr._selection_locks = SimpleNamespace(
        acquire_lock=lambda _umo: AsyncMock(
            __aenter__=AsyncMock(return_value=None),
            __aexit__=AsyncMock(return_value=False),
        )
    )
    mgr._load_selection = AsyncMock(return_value="cid-1")
    mgr._delete_records = AsyncMock()
    mgr.on_current_conversation_deleted = None
    mgr.session_conversations = {"p:FriendMessage:u1": "cid-1"}
    mgr._on_conversation_deleted_callbacks = []
    monkeypatch.setattr(sp, "session_remove", AsyncMock())

    received: list[tuple[str, str]] = []

    async def on_deleted(umo: str, cid: str) -> None:
        received.append((umo, cid))

    mgr.register_on_conversation_deleted(on_deleted)
    await mgr.delete_conversation("p:FriendMessage:u1")

    assert received == [("p:FriendMessage:u1", "cid-1")]


@pytest.mark.asyncio
async def test_subagent_service_evicts_idle_callers_and_defers_deleted_active_scope():
    """SubAgentService evicts idle callers, keeps active ones, and cleans up on settle."""
    from astrbot.core.astr_agent_runtime.subagents.context import SubAgentContext
    from astrbot.core.astr_agent_runtime.subagents.service import SubAgentService
    from astrbot.core.astr_agent_runtime.subagents.store import (
        AgentRecord,
        AgentScope,
        AgentState,
        SubAgentStore,
        TaskRecord,
    )

    store = SubAgentStore(MagicMock())
    service = SubAgentService(store, {}, max_cached_callers=2)

    scope1 = AgentScope("p:FriendMessage:u1", "c1")
    scope2 = AgentScope("p:FriendMessage:u2", "c2")
    scope3 = AgentScope("p:FriendMessage:u3", "c3")

    active_record = AgentRecord(
        agent_id="agent-1",
        scope=scope1,
        runtime="astrbot",
        name="worker",
        conversation_id="sub-1",
        options={},
        owner={"sender_id": "u1"},
        parent=SimpleNamespace(runtime="astrbot", session_id="c1"),
        turns=[
            TaskRecord(1, [{"type": "text", "text": "hi"}], state=AgentState.RUNNING)
        ],
    )
    store.agents[active_record.agent_id] = active_record

    def real_ctx(scope: AgentScope) -> SubAgentContext:
        ctx = SubAgentContext.__new__(SubAgentContext)
        event = MagicMock()
        event.get_extra.return_value = None
        ctx.context = MagicMock()
        ctx.event = event
        ctx.subagent_scope = scope
        ctx.is_subagent = False
        ctx.agent_session = SimpleNamespace(
            runtime="astrbot", session_id=scope.conversation_id
        )
        ctx.delegable_tools = MagicMock()
        return ctx

    service._caller(real_ctx(scope1))
    service._caller(real_ctx(scope2))
    service._caller(real_ctx(scope3))

    assert scope1 in service._callers
    assert scope2 not in service._callers
    assert scope3 in service._callers

    # Deletion while active defers cleanup until work settles.
    service.evict_scope("p:FriendMessage:u1", "c1")
    assert scope1 in service._callers
    active_record.turns[0].state = AgentState.COMPLETED
    service.on_scope_settled(scope1)
    assert scope1 not in service._callers
    assert scope3 in service._callers
