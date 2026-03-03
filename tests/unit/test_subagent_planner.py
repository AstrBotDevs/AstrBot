from __future__ import annotations

from types import SimpleNamespace

import pytest

from astrbot.core.agent.tool import FunctionTool
from astrbot.core.subagent.codec import decode_subagent_config
from astrbot.core.subagent.planner import SubagentPlanner


class _FakeToolMgr:
    def __init__(self):
        self.func_list = [
            FunctionTool(
                name="tool_a",
                description="A",
                parameters={"type": "object", "properties": {}},
                handler=None,
            ),
            FunctionTool(
                name="tool_b",
                description="B",
                parameters={"type": "object", "properties": {}},
                handler=None,
            ),
        ]


class _FakePersonaMgr:
    async def get_persona(self, persona_id: str):
        if persona_id == "missing":
            raise ValueError("missing")
        return SimpleNamespace(
            system_prompt="persona prompt",
            tools=["tool_b"],
            begin_dialogs=[{"role": "assistant", "content": "hi"}],
        )


@pytest.mark.asyncio
async def test_planner_builds_handoff_and_dedupe_set():
    config, _ = decode_subagent_config(
        {
            "main_enable": True,
            "remove_main_duplicate_tools": True,
            "agents": [
                {
                    "name": "writer",
                    "enabled": True,
                    "tools_scope": "list",
                    "tools": ["tool_a", "transfer_to_x", "not_exist"],
                    "instructions": "x",
                    "max_steps": 7,
                }
            ],
        }
    )
    planner = SubagentPlanner(_FakeToolMgr(), _FakePersonaMgr())
    plan = await planner.build_mount_plan(config)
    assert len(plan.handoffs) == 1
    assert "transfer_to_writer" in plan.handoff_by_tool_name
    assert "tool_a" in plan.main_tool_exclude_set
    assert all("transfer_to_x" not in msg for msg in plan.main_tool_exclude_set)
    assert any("recursive handoff" in d for d in plan.diagnostics)
    assert getattr(plan.handoffs[0], "max_steps", None) == 7


@pytest.mark.asyncio
async def test_planner_uses_persona_tools_and_prompt():
    config, _ = decode_subagent_config(
        {
            "main_enable": True,
            "agents": [
                {
                    "name": "persona_agent",
                    "enabled": True,
                    "persona_id": "p1",
                    "tools_scope": "persona",
                }
            ],
        }
    )
    planner = SubagentPlanner(_FakeToolMgr(), _FakePersonaMgr())
    plan = await planner.build_mount_plan(config)
    assert len(plan.handoffs) == 1
    handoff = plan.handoffs[0]
    assert handoff.agent.tools == ["tool_b"]
    assert handoff.agent.instructions == "persona prompt"


@pytest.mark.asyncio
async def test_planner_detects_safe_tool_name_conflict():
    config, _ = decode_subagent_config(
        {
            "main_enable": True,
            "agents": [
                {"name": "A A", "enabled": True, "tools_scope": "none"},
                {"name": "a_a", "enabled": True, "tools_scope": "none"},
            ],
        }
    )
    planner = SubagentPlanner(_FakeToolMgr(), _FakePersonaMgr())
    plan = await planner.build_mount_plan(config)
    assert len(plan.handoffs) == 2
    assert plan.handoffs[0].name == "transfer_to_a_a"
    assert plan.handoffs[1].name == "transfer_to_a_a-2"
    assert any(
        "duplicate subagent tool name" in d and "renamed" in d
        for d in plan.diagnostics
    )


@pytest.mark.asyncio
async def test_planner_respects_tools_scope_all_and_none():
    config, _ = decode_subagent_config(
        {
            "main_enable": True,
            "agents": [
                {"name": "all_agent", "enabled": True, "tools_scope": "all"},
                {"name": "none_agent", "enabled": True, "tools_scope": "none"},
            ],
        }
    )
    planner = SubagentPlanner(_FakeToolMgr(), _FakePersonaMgr())
    plan = await planner.build_mount_plan(config)
    by_name = {handoff.agent.name: handoff for handoff in plan.handoffs}
    assert by_name["all_agent"].agent.tools is None
    assert by_name["none_agent"].agent.tools == []


@pytest.mark.asyncio
async def test_planner_safe_tool_name_is_stable():
    config, _ = decode_subagent_config(
        {
            "main_enable": True,
            "agents": [
                {
                    "name": "Writer Agent !!!",
                    "enabled": True,
                    "tools_scope": "none",
                }
            ],
        }
    )
    planner = SubagentPlanner(_FakeToolMgr(), _FakePersonaMgr())
    plan1 = await planner.build_mount_plan(config)
    plan2 = await planner.build_mount_plan(config)
    assert len(plan1.handoffs) == 1
    assert len(plan2.handoffs) == 1
    assert plan1.handoffs[0].name == plan2.handoffs[0].name
