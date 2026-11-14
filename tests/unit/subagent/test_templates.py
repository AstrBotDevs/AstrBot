from copy import deepcopy
from types import SimpleNamespace

import pytest

from astrbot.core.astr_agent_runtime.main_agent import persona as persona_build
from astrbot.core.skills.skill_manager import SkillInfo


@pytest.mark.asyncio
@pytest.mark.parametrize("persona_id", [None, "default", "missing"])
async def test_persona_resolution_occurs_in_native_runtime(environment, persona_id):
    env = environment
    dialogs = [{"role": "assistant", "content": "Opening"}]
    persona = {
        "prompt": "Persona instructions",
        "tools": None,
        "_begin_dialogs_processed": dialogs,
    }
    env.context.persona_manager.get_persona_v3_by_id.side_effect = lambda value: (
        deepcopy(persona) if value == "default" else None
    )
    profile = env.context.get_config()
    profile["agent"]["config"]["persona"] = {
        "persona_id": "",
        "system_prompt": "Parent instructions",
        "tools": ["tool_a"],
    }
    env.context.get_config = lambda **kwargs: profile
    selected = await env.save_agent("planner", persona_id=persona_id)
    if persona_id == "missing":
        with pytest.raises(ValueError, match="persona"):
            await env.native.spawn_agent(
                env.root,
                [{"type": "plain", "text": "Task"}],
                config_id=selected.config_id,
            )
        return
    agent = await env.native.spawn_agent(
        env.root, [{"type": "plain", "text": "Task"}], config_id=selected.config_id
    )
    await env.service.wait(env.root, [agent["agent_id"]], 2000, "all")
    data = (
        await env.db.get_preference(
            "subagent_native", "conversation", agent["conversation_id"]
        )
    ).value
    assert data["instructions"] == (
        "Persona instructions" if persona_id == "default" else "Parent instructions"
    )
    assert data["tools"] == (None if persona_id == "default" else ["tool_a"])
    assert data["initial_dialogs"] == (dialogs if persona_id == "default" else [])


@pytest.mark.asyncio
async def test_expert_changes_do_not_reconfigure_open_conversations(environment):
    env = environment
    persona = {"prompt": "Original instructions", "tools": []}
    env.context.persona_manager.get_persona_v3_by_id.side_effect = lambda _: deepcopy(
        persona
    )
    selected = await env.save_agent(
        "researcher", persona_id="researcher", provider_id="alternate"
    )
    agent = await env.native.spawn_agent(
        env.root, [{"type": "plain", "text": "Initial"}], config_id=selected.config_id
    )
    await env.service.wait(env.root, [agent["agent_id"]], 2000, "all")
    persona["prompt"] = "Updated instructions"
    selected.config["model"]["provider_id"] = "model"
    await env.agent_configs.save(selected)
    await env.service.send(
        env.root, agent["agent_id"], [{"type": "plain", "text": "Continue"}]
    )
    await env.service.wait(env.root, [agent["agent_id"]], 2000, "all")
    assert env.context.provider_manager.get_provider_by_id.call_args.args == (
        "alternate",
    )
    assert "Original instructions" in str(
        env.provider.text_chat.call_args.kwargs["contexts"]
    )
    assert "Updated instructions" not in str(
        env.provider.text_chat.call_args.kwargs["contexts"]
    )


@pytest.mark.asyncio
async def test_temporary_persona_dialogue_is_used_once_but_not_saved_as_history(
    environment,
):
    env = environment
    env.context.persona_manager.get_persona_v3_by_id.return_value = {
        "prompt": "Instructions",
        "tools": [],
        "_begin_dialogs_processed": [
            {"role": "user", "content": "Temporary setup", "_no_save": True}
        ],
    }
    selected = await env.save_agent("expert", persona_id="default")
    agent = await env.native.spawn_agent(
        env.root, [{"type": "plain", "text": "Initial"}], config_id=selected.config_id
    )
    await env.service.wait(env.root, [agent["agent_id"]], 2000, "all")
    assert "Temporary setup" in str(env.provider.text_chat.call_args.kwargs["contexts"])
    row = (
        await env.db.get_preference(
            "subagent_native", "conversation", agent["conversation_id"]
        )
    ).value
    assert "Temporary setup" not in str(row["messages"])
    await env.service.send(
        env.root, agent["agent_id"], [{"type": "plain", "text": "Continue"}]
    )
    await env.service.wait(env.root, [agent["agent_id"]], 2000, "all")
    assert "Temporary setup" not in str(
        env.provider.text_chat.call_args.kwargs["contexts"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("selection", [None, [], ["authorized_skill"]])
async def test_native_skills_combine_runtime_and_authorized_plugin_selection(
    environment, monkeypatch, selection
):
    env = environment
    local = SkillInfo("runtime_skill", "Runtime skill", "runtime/SKILL.md", True)
    authorized = SkillInfo(
        "authorized_skill",
        "Authorized skill",
        "plugin/SKILL.md",
        True,
        source_type="plugin",
        plugin_name="test_plugin",
    )
    excluded = SkillInfo(
        "excluded_skill",
        "Excluded skill",
        "excluded/SKILL.md",
        True,
        source_type="plugin",
        plugin_name="test_plugin",
    )
    monkeypatch.setattr(
        persona_build,
        "SkillManager",
        lambda: SimpleNamespace(list_skills=lambda **_: [local, excluded]),
    )
    monkeypatch.setattr(
        persona_build.plugins,
        "star_registry",
        [
            SimpleNamespace(
                root_dir_name="test_plugin",
                name="test-plugin",
                activated=True,
                reserved=False,
            )
        ],
    )
    env.root.plugin_skills = [authorized]
    env.context.persona_manager.get_persona_v3_by_id.return_value = {
        "prompt": "Expert instructions",
        "tools": [],
        "skills": selection,
    }
    selected = await env.save_agent("expert", persona_id="default")
    agent = await env.native.spawn_agent(
        env.root, [{"type": "plain", "text": "Task"}], config_id=selected.config_id
    )
    await env.service.wait(env.root, [agent["agent_id"]], 2000, "all")
    prompt = str(env.provider.text_chat.call_args.kwargs["contexts"])
    assert ("authorized_skill" in prompt) == (selection != [])
    assert ("runtime_skill" in prompt) == (selection is None)
    assert "excluded_skill" not in prompt
