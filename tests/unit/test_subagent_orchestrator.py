from copy import deepcopy
from unittest.mock import MagicMock, patch

import pytest

from astrbot.core.subagent_orchestrator import SubAgentOrchestrator


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
