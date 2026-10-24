import json
from asyncio import Queue
from copy import deepcopy
from unittest.mock import MagicMock, patch

import pytest

from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.star.context import Context
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
async def test_config_load_preserves_plugin_experts_without_native_settings(tmp_path):
    """Configuration cleanup retains legacy plugin data without core routing."""
    agents = _build_cfg({})["agents"]
    config_path = tmp_path / "legacy.json"
    config_path.write_text(
        json.dumps(
            {
                "subagent_orchestrator": {
                    "agents": agents,
                    "main_enable": True,
                    "router_system_prompt": "Legacy routing",
                    "remove_main_duplicate_tools": True,
                }
            }
        ),
        encoding="utf-8",
    )
    config = AstrBotConfig(
        str(config_path),
        default_config={
            "subagent_orchestrator": DEFAULT_CONFIG["subagent_orchestrator"]
        },
    )
    assert config["subagent_orchestrator"] == {"agents": agents}
    assert json.loads(config_path.read_text(encoding="utf-8-sig")) == dict(config)
    persona_mgr = MagicMock()
    persona_mgr.get_persona_v3_by_id.return_value = None
    orchestrator = SubAgentOrchestrator(MagicMock(), persona_mgr)
    await orchestrator.reload_from_config(config["subagent_orchestrator"])
    assert orchestrator.handoffs[0].agent.name == "planner"


@pytest.mark.asyncio
async def test_context_retains_live_orchestrator_and_can_reload_experts():
    """Plugins can still read and reload configuration-driven experts."""
    persona_mgr = MagicMock()
    persona_mgr.get_persona_v3_by_id.return_value = None
    orchestrator = SubAgentOrchestrator(MagicMock(), persona_mgr)
    context = Context(
        Queue(),
        {},
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        persona_mgr,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        subagent_orchestrator=orchestrator,
    )
    assert context.subagent_orchestrator is orchestrator
    await context.subagent_orchestrator.reload_from_config(_build_cfg({}))
    assert context.subagent_orchestrator.handoffs[0].agent.name == "planner"
    await context.subagent_orchestrator.reload_from_config(
        _build_cfg({"name": "butler"})
    )
    assert [tool.agent.name for tool in context.subagent_orchestrator.handoffs] == [
        "butler"
    ]


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
