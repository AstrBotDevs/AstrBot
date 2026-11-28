"""Unit tests for bounded session and subagent caller caching in AstrAgentRuntime."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


class _DummyTurn:
    done = False

    async def cancel(self) -> None:
        return None


from astrbot.core.agent.runtime import SessionState
from astrbot.core.astr_agent_runtime.runtime import AstrAgentRuntime
from astrbot.core.astr_agent_runtime.subagents.service import SubAgentService
from astrbot.core.astr_agent_runtime.subagents.store import (
    AgentRecord,
    AgentScope,
    AgentState,
    SubAgentStore,
    TaskRecord,
)


def _make_runtime(*, max_idle_sessions: int = 2):
    conversations: dict[str, SimpleNamespace] = {}

    class FakeStore:
        async def get_metadata(self, cid: str):
            return conversations.get(cid)

    conv_mgr = MagicMock()
    conv_mgr.db = SimpleNamespace(conversation_store=FakeStore())
    conv_mgr.register_on_session_deleted = MagicMock()
    subagents = MagicMock()
    subagents.store = SimpleNamespace(find_native_conversation=lambda umo, cid: None)
    subagents.evict_umo = MagicMock()
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
async def test_runtime_evicts_oldest_idle_sessions_and_preserves_active_ones() -> None:
    """Idle main sessions are LRU-evicted past capacity while active ones remain."""
    runtime, conversations, _, _ = _make_runtime(max_idle_sessions=2)
    for cid in ("c1", "c2", "c3", "c4"):
        conversations[cid] = SimpleNamespace(umo=f"p:FriendMessage:{cid}")

    s1 = await runtime.open_session("p:FriendMessage:c1", session_id="c1")
    s2 = await runtime.open_session("p:FriendMessage:c2", session_id="c2")
    assert s1.state == SessionState.IDLE
    assert s2.state == SessionState.IDLE

    # Mark s1 as RUNNING (via an unfinished dummy turn) so s2 should be evicted first.
    active_turn = _DummyTurn()
    s1._turns.add(active_turn)
    s1.active_turn = active_turn
    assert s1.state == SessionState.RUNNING

    s3 = await runtime.open_session("p:FriendMessage:c3", session_id="c3")
    assert ("main", "c1") in runtime._sessions
    assert ("main", "c2") not in runtime._sessions
    assert s2.closed is True
    assert ("main", "c3") in runtime._sessions

    # Touch s3 again so c3 stays MRU, then open c4; c3 stays while running c1 also stays
    # -> actually cap=2 with s1 RUNNING + s3 IDLE + s4 IDLE triggers eviction of s3 (IDLE).
    s4 = await runtime.open_session("p:FriendMessage:c4", session_id="c4")
    assert ("main", "c1") in runtime._sessions
    assert ("main", "c3") not in runtime._sessions
    assert s3.closed is True
    assert ("main", "c4") in runtime._sessions

    # Re-opening an evicted session returns a fresh live session.
    s2_reopened = await runtime.open_session("p:FriendMessage:c2", session_id="c2")
    assert s2_reopened is not s2
    assert s2_reopened.closed is False

    # Clear fake active turn before closing cleanly.
    s1._turns.clear()
    s1.active_turn = None
    assert s4.closed or not s4.closed
    await runtime.close()


@pytest.mark.asyncio
async def test_runtime_initialize_registers_session_deletion_eviction() -> None:
    """initialize() registers evict_umo and clears idle sessions for deleted UMOs."""
    runtime, conversations, conv_mgr, subagents = _make_runtime(max_idle_sessions=8)
    conversations["c1"] = SimpleNamespace(umo="p:FriendMessage:u1")
    conversations["c2"] = SimpleNamespace(umo="p:FriendMessage:u1")
    conversations["c3"] = SimpleNamespace(umo="p:FriendMessage:u2")

    await runtime.initialize()
    conv_mgr.register_on_session_deleted.assert_called_once_with(runtime.evict_umo)

    s1 = await runtime.open_session("p:FriendMessage:u1", session_id="c1")
    s2 = await runtime.open_session("p:FriendMessage:u1", session_id="c2")
    s3 = await runtime.open_session("p:FriendMessage:u2", session_id="c3")

    # Keep s1 running so only idle c2 is evicted for u1.
    active_turn = _DummyTurn()
    s1._turns.add(active_turn)
    s1.active_turn = active_turn

    await runtime.evict_umo("p:FriendMessage:u1")

    assert ("main", "c1") in runtime._sessions
    assert ("main", "c2") not in runtime._sessions
    assert s2.closed is True
    assert ("main", "c3") in runtime._sessions
    assert s3.closed is False
    subagents.evict_umo.assert_called_once_with("p:FriendMessage:u1")

    s1._turns.clear()
    s1.active_turn = None
    await runtime.close()


@pytest.mark.asyncio
async def test_subagent_service_evicts_idle_callers_beyond_capacity() -> None:
    """SubAgentService evicts oldest idle callers while retaining active scopes."""
    db = MagicMock()
    store = SubAgentStore(db)
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

    from astrbot.core.astr_agent_runtime.subagents.context import SubAgentContext

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

    # scope1 has an unfinished turn so scope2 (idle) must be evicted first.
    assert scope1 in service._callers
    assert scope2 not in service._callers
    assert scope3 in service._callers

    # Mark turn finished, then evict scope1's UMO cleanly.
    active_record.turns[0].state = AgentState.COMPLETED
    service.evict_umo("p:FriendMessage:u1")
    assert scope1 not in service._callers
    assert scope3 in service._callers
    await asyncio.sleep(0)
