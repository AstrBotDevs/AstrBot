from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.agent import Agent
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.subagent.models import SubagentMountPlan
from astrbot.core.subagent_orchestrator import SubAgentOrchestrator


@pytest.mark.asyncio
async def test_reload_from_config_applies_runtime_worker_and_nested_depth_settings():
    tool_mgr = MagicMock()
    persona_mgr = MagicMock()
    persona_mgr.db = None
    orchestrator = SubAgentOrchestrator(tool_mgr, persona_mgr)
    orchestrator._planner.build_mount_plan = AsyncMock(return_value=SubagentMountPlan())  # type: ignore[method-assign]

    diagnostics = await orchestrator.reload_from_config(
        {
            "main_enable": True,
            "max_concurrent_subagent_runs": 11,
            "max_nested_depth": 4,
            "runtime": {
                "max_attempts": 5,
                "base_delay_ms": 700,
                "max_delay_ms": 9000,
                "jitter_ratio": 0.3,
            },
            "worker": {
                "poll_interval": 2.0,
                "batch_size": 6,
                "error_retry_max_interval": 25.0,
            },
            "agents": [{"name": "writer"}],
        }
    )

    assert diagnostics == []
    assert orchestrator.get_max_nested_depth() == 4
    assert orchestrator.get_config().runtime.max_attempts == 5
    assert orchestrator.get_config().worker.poll_interval == pytest.approx(2.0)
    assert orchestrator._runtime._max_concurrent == 11
    assert orchestrator._runtime._max_attempts == 5
    assert orchestrator._runtime._base_delay_ms == 700
    assert orchestrator._runtime._max_delay_ms == 9000
    assert orchestrator._runtime._jitter_ratio == pytest.approx(0.3)
    assert orchestrator._worker._poll_interval == pytest.approx(2.0)
    assert orchestrator._worker._batch_size == 6
    assert orchestrator._worker._error_retry_max_interval == pytest.approx(25.0)


def test_build_handoff_snapshot_preserves_unlimited_max_steps_flag():
    handoff = HandoffTool(agent=Agent(name="writer", instructions="prompt", tools=[]))
    handoff.max_steps = None
    handoff.max_steps_unlimited = True  # type: ignore[attr-defined]

    snapshot = SubAgentOrchestrator._build_handoff_snapshot(handoff)

    assert snapshot["max_steps"] is None
    assert snapshot["max_steps_unlimited"] is True
