from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from astrbot.core.agent.message import Message
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.subagent_orchestrator import SubAgentOrchestrator
from astrbot.core.subagent_runner import (
    SubAgentSessionManager,
    normalize_context_persistence,
)


def _build_cfg(agent_overrides: dict) -> dict:
    agent = {
        "name": "planner",
        "enabled": True,
        "persona_id": None,
        "system_prompt": "inline prompt",
        "public_description": "",
        "tools": ["tool_a", " ", "tool_b"],
    }
    agent.update(agent_overrides)
    return {"agents": [agent]}


@pytest.mark.asyncio
async def test_reload_from_config_default_persona_is_resolved():
    tool_mgr = MagicMock()
    persona_mgr = MagicMock()
    default_persona = {
        "name": "default",
        "prompt": "You are a helpful and friendly assistant.",
        "tools": None,
        "_begin_dialogs_processed": [],
    }
    persona_mgr.get_persona_v3_by_id.return_value = deepcopy(default_persona)
    orchestrator = SubAgentOrchestrator(tool_mgr=tool_mgr, persona_mgr=persona_mgr)

    await orchestrator.reload_from_config(_build_cfg({"persona_id": "default"}))

    assert len(orchestrator.handoffs) == 1
    handoff = orchestrator.handoffs[0]
    assert handoff.agent.instructions == default_persona["prompt"]
    assert handoff.agent.tools is None
    assert handoff.agent.begin_dialogs == default_persona["_begin_dialogs_processed"]


@pytest.mark.asyncio
async def test_reload_from_config_missing_persona_falls_back_to_inline_and_warns():
    tool_mgr = MagicMock()
    persona_mgr = MagicMock()
    persona_mgr.get_persona_v3_by_id.return_value = None
    orchestrator = SubAgentOrchestrator(tool_mgr=tool_mgr, persona_mgr=persona_mgr)

    with patch("astrbot.core.subagent_orchestrator.logger") as mock_logger:
        await orchestrator.reload_from_config(_build_cfg({"persona_id": "not_exists"}))

    assert len(orchestrator.handoffs) == 1
    handoff = orchestrator.handoffs[0]
    assert handoff.agent.instructions == "inline prompt"
    assert handoff.agent.tools == ["tool_a", "tool_b"]
    assert handoff.agent.begin_dialogs is None
    mock_logger.warning.assert_called_once_with(
        "SubAgent persona %s not found, fallback to inline prompt.",
        "not_exists",
    )


@pytest.mark.asyncio
async def test_reload_from_config_uses_processed_begin_dialogs_and_deepcopy():
    tool_mgr = MagicMock()
    persona_mgr = MagicMock()
    processed_dialogs = [{"role": "user", "content": "hello", "_no_save": True}]
    persona_mgr.get_persona_v3_by_id.return_value = {
        "name": "custom",
        "prompt": "persona prompt",
        "tools": ["tool_from_persona"],
        "_begin_dialogs_processed": processed_dialogs,
    }
    orchestrator = SubAgentOrchestrator(tool_mgr=tool_mgr, persona_mgr=persona_mgr)

    await orchestrator.reload_from_config(_build_cfg({"persona_id": "custom"}))
    processed_dialogs[0]["content"] = "mutated"

    handoff = orchestrator.handoffs[0]
    assert handoff.agent.instructions == "persona prompt"
    assert handoff.agent.tools == ["tool_from_persona"]
    assert handoff.agent.begin_dialogs[0]["content"] == "hello"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_tools", "expected_tools"),
    [
        (None, None),
        ([], []),
        ("not-a-list", []),
    ],
)
async def test_reload_from_config_tool_normalization(raw_tools, expected_tools):
    tool_mgr = MagicMock()
    persona_mgr = MagicMock()
    persona_mgr.get_persona_v3_by_id.return_value = {
        "name": "custom",
        "prompt": "persona prompt",
        "tools": raw_tools,
        "_begin_dialogs_processed": [],
    }
    orchestrator = SubAgentOrchestrator(tool_mgr=tool_mgr, persona_mgr=persona_mgr)

    await orchestrator.reload_from_config(_build_cfg({"persona_id": "custom"}))

    handoff = orchestrator.handoffs[0]
    assert handoff.agent.tools == expected_tools


def test_normalize_context_persistence_defaults_ttl_to_one_hour():
    assert normalize_context_persistence(None) == {
        "enable": False,
        "max_turns": 10,
        "ttl_seconds": 3600,
    }


def test_normalize_context_persistence_allows_ttl_without_expiry():
    assert normalize_context_persistence({"ttl_seconds": -1})["ttl_seconds"] == -1


@pytest.mark.asyncio
async def test_reload_from_config_binds_context_persistence_defaults():
    tool_mgr = MagicMock()
    persona_mgr = MagicMock()
    persona_mgr.get_persona_v3_by_id.return_value = None
    orchestrator = SubAgentOrchestrator(tool_mgr=tool_mgr, persona_mgr=persona_mgr)

    await orchestrator.reload_from_config(_build_cfg({}))

    handoff = orchestrator.handoffs[0]
    assert handoff.context_persistence["enable"] is False
    assert handoff.context_persistence["ttl_seconds"] == 3600
    assert isinstance(handoff.config_fingerprint, str)


def test_subagent_session_manager_expires_by_ttl_and_fingerprint():
    manager = SubAgentSessionManager()
    key = ("umo", "session", "planner")
    config = normalize_context_persistence({"enable": True})
    messages = [Message(role="user", content="remember me")]

    manager.set_messages(
        key,
        messages,
        config_fingerprint="a",
        context_persistence=config,
        now=100.0,
    )

    assert manager.get_messages(
        key,
        ttl_seconds=3600,
        config_fingerprint="a",
        now=200.0,
    )
    assert (
        manager.get_messages(
            key,
            ttl_seconds=10,
            config_fingerprint="a",
            now=200.0,
        )
        is None
    )

    manager.set_messages(
        key,
        messages,
        config_fingerprint="a",
        context_persistence=config,
        now=300.0,
    )
    assert manager.get_messages(
        key,
        ttl_seconds=-1,
        config_fingerprint="a",
        now=999999.0,
    )

    manager.set_messages(
        key,
        messages,
        config_fingerprint="a",
        context_persistence=config,
        now=300.0,
    )
    assert (
        manager.get_messages(
            key,
            ttl_seconds=3600,
            config_fingerprint="b",
            now=301.0,
        )
        is None
    )


def test_subagent_session_manager_trim_preserves_tool_call_pairs():
    manager = SubAgentSessionManager()
    tool_call = {
        "type": "function",
        "id": "call-1",
        "function": {"name": "lookup", "arguments": "{}"},
    }
    messages = [
        Message(role="system", content="system"),
        Message(role="user", content="old"),
        Message(role="assistant", content="old reply"),
        Message(role="user", content="new"),
        Message(role="assistant", content=None, tool_calls=[tool_call]),
        Message(role="tool", content="tool result", tool_call_id="call-1"),
        Message(role="assistant", content="final"),
    ]
    key = ("umo", "session", "planner")

    manager.set_messages(
        key,
        messages,
        config_fingerprint="fp",
        context_persistence={
            "enable": True,
            "max_turns": 1,
            "ttl_seconds": 3600,
        },
        now=100.0,
    )

    trimmed = manager.get_messages(
        key,
        ttl_seconds=3600,
        config_fingerprint="fp",
        now=101.0,
    )
    assert [message.role for message in trimmed] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert trimmed[1].tool_calls
    assert trimmed[2].tool_call_id == "call-1"


def test_subagent_session_manager_matches_non_string_dict_tool_call_id():
    manager = SubAgentSessionManager()
    key = ("umo", "session", "planner")
    messages = [
        Message(
            role="assistant",
            content=None,
            tool_calls=[
                {
                    "type": "function",
                    "id": 123,
                    "function": {"name": "lookup", "arguments": "{}"},
                }
            ],
        ),
        Message(role="tool", content="tool result", tool_call_id="123"),
    ]

    manager.set_messages(
        key,
        messages,
        config_fingerprint="fp",
        context_persistence={
            "enable": True,
            "max_turns": 10,
            "ttl_seconds": 3600,
        },
        现在=100.0，
    )

    trimmed = manager.get_messages(
        key,
        ttl_seconds=3600,
        config_fingerprint="fp",
        现在=101.0,
    )

    assert [message.role for message in trimmed] == ["assistant", "tool"]
    assert trimmed[1].tool_call_id == "123"


@pytest.mark.asyncio
async def test_subagent_session_manager_clear_removes_only_idle_locks():
    manager = SubAgentSessionManager()
    key = ("umo", "session", "planner")
    idle_lock = manager.get_lock(key)

    manager.clear(key)

    assert key not in manager._locks
    held_lock = manager.get_lock(key)

    async with held_lock:
        manager.clear(key)
        assert manager.get_lock(key) is held_lock

    assert manager.get_lock(key) is held_lock
    assert held_lock is not idle_lock


def test_subagent_session_manager_key_uses_session_and_agent():
    event = MagicMock()
    event.unified_msg_origin = "webchat:FriendMessage:webchat!user!session"
    event.session_id = "webchat!user!session"
    run_context = ContextWrapper(context=SimpleNamespace(event=event))

    key = SubAgentSessionManager().build_key(run_context, "planner")

    assert key == (
        "webchat:FriendMessage:webchat!user!session",
        "webchat!user!session",
        "planner",
    )
