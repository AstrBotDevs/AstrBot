from types import SimpleNamespace

import pytest
import pytest_asyncio

import astrbot.api  # Initialize the public API before importing persona modules.
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.persona_mgr import PersonaManager
from astrbot.core.provider.func_tool_manager import FunctionToolManager
from astrbot.core.subagent_orchestrator import SubAgentOrchestrator
from astrbot.dashboard.services.persona_service import PersonaService


@pytest_asyncio.fixture
async def persona_core(tmp_path):
    db = SQLiteDatabase(str(tmp_path / "personas.db"))
    await db.initialize()
    db.inited = True
    try:
        manager = PersonaManager(db, SimpleNamespace(default_conf={}))
        await manager.initialize()
        await manager.create_persona(
            "custom", "Old prompt", ["Old question", "Old answer"], tools=["old_tool"]
        )
        config = {
            "agents": [
                {"name": "planner", "persona_id": "custom"},
                {"name": "inline", "system_prompt": "Inline prompt", "tools": []},
            ]
        }
        orchestrator = SubAgentOrchestrator(FunctionToolManager(), manager)
        await orchestrator.reload_from_config(config)
        yield SimpleNamespace(
            persona_mgr=manager,
            subagent_orchestrator=orchestrator,
            astrbot_config={"subagent_orchestrator": config},
        )
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_persona_update_refreshes_subagent_without_saving_config(persona_core):
    service = PersonaService(persona_core)
    orchestrator = persona_core.subagent_orchestrator
    previous_handoff = orchestrator.handoffs[0]
    assert previous_handoff.agent.instructions == "Old prompt"

    await service.update_persona(
        {
            "persona_id": "custom",
            "system_prompt": "New prompt",
            "begin_dialogs": ["New question", "New answer"],
            "tools": ["new_tool"],
        }
    )

    persisted = await persona_core.persona_mgr.get_persona("custom")
    assert persisted.system_prompt == "New prompt"
    agent = orchestrator.handoffs[0].agent
    assert agent.instructions == "New prompt"
    assert agent.begin_dialogs == [
        {"role": "user", "content": "New question", "_no_save": True},
        {"role": "assistant", "content": "New answer", "_no_save": True},
    ]
    assert agent.tools == ["new_tool"]
    assert orchestrator.handoffs[1].agent.instructions == "Inline prompt"
    assert orchestrator.handoffs[1].agent.tools == []
    # Requests already holding a handoff keep their existing snapshot.
    assert previous_handoff.agent.instructions == "Old prompt"


@pytest.mark.asyncio
async def test_failed_persona_update_does_not_replace_handoffs(persona_core):
    previous_handoffs = persona_core.subagent_orchestrator.handoffs
    with pytest.raises(ValueError, match="does not exist"):
        await PersonaService(persona_core).update_persona(
            {"persona_id": "missing", "system_prompt": "New prompt"}
        )
    assert persona_core.subagent_orchestrator.handoffs is previous_handoffs


@pytest.mark.asyncio
async def test_persona_update_without_subagent_orchestrator(persona_core):
    persona_core.subagent_orchestrator = None
    await PersonaService(persona_core).update_persona(
        {"persona_id": "custom", "system_prompt": "New prompt"}
    )
    persona = await persona_core.persona_mgr.get_persona("custom")
    assert persona.system_prompt == "New prompt"


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_config", [None, [], "invalid", False])
async def test_persona_update_with_non_object_subagent_config(persona_core, invalid_config):
    persona_core.astrbot_config["subagent_orchestrator"] = invalid_config
    result = await PersonaService(persona_core).update_persona(
        {"persona_id": "custom", "system_prompt": "New prompt"}
    )
    assert result == {"message": "人格更新成功"}
    persona = await persona_core.persona_mgr.get_persona("custom")
    assert persona.system_prompt == "New prompt"
    assert persona_core.subagent_orchestrator.handoffs == []
