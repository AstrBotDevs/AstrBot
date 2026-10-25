import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from astrbot.api.web import PluginRequest, bind_request_context
from astrbot.core.agent.agent import Agent
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.config.astrbot_config import AstrBotConfig


async def call_settings(env, method, body=None):
    """Call the registered handler using the real plugin request wrapper.

    Args:
        env: Plugin fixture with runtime state and services.
        method: HTTP method to dispatch.
        body: Optional JSON payload.

    Returns:
        Response and decoded JSON body.
    """

    async def receive():
        return {"type": "http.request", "body": json.dumps(body).encode()}

    raw = Request(
        {
            "type": "http",
            "method": method,
            "path": "/experts",
            "headers": [(b"content-type", b"application/json")],
            "query_string": b"",
        },
        receive=receive,
    )
    with bind_request_context(PluginRequest(raw, username="admin")):
        response = await env.plugin.expert_settings()
    return response, json.loads(response.body)


@pytest.fixture
def saved_config(environment, tmp_path):
    config = AstrBotConfig(
        str(tmp_path / "experts.json"),
        default_config={"enabled": True, "max_steps": 17, "agents": []},
    )
    environment.plugin.config = config
    return config


@pytest.mark.asyncio
async def test_expert_options_do_not_expose_provider_credentials(environment):
    env = environment
    env.context.provider_manager.provider_insts = [
        SimpleNamespace(
            provider_config={"id": "model", "api_key": "not-for-the-view"},
            get_model=lambda: "example-model",
        )
    ]
    env.context.persona_manager.personas_v3 = [
        {"name": "research", "prompt": "Research carefully", "tools": ["lookup"]}
    ]
    env.manager.func_list.extend(
        [
            FunctionTool(name="lookup", description="Look up facts", parameters={}),
            FunctionTool(
                name="inactive", description="Inactive", parameters={}, active=False
            ),
            HandoffTool(Agent(name="legacy")),
        ]
    )
    response, payload = await call_settings(env, "GET")
    assert response.status_code == 200
    assert payload["data"]["providers"] == [{"id": "model", "model": "example-model"}]
    assert payload["data"]["personas"][0]["prompt"] == "Research carefully"
    assert payload["data"]["tools"] == [
        {"name": "lookup", "description": "Look up facts"}
    ]
    assert "not-for-the-view" not in response.body.decode()


@pytest.mark.asyncio
async def test_expert_crud_persists_and_updates_spawn_without_restarting_workers(
    environment, saved_config
):
    env = environment
    env.context.persona_manager.get_persona_v3_by_id.return_value = None
    spawn = env.plugin.spawn_tool
    spawn.active = False
    worker = env.runtime.create_instance(
        agent=Agent(name="existing"), parent_context=env.wrapper, task="In progress"
    )
    payload = {
        "agents": [
            {"name": "researcher", "system_prompt": "Find evidence", "tools": None}
        ]
    }
    response, data = await call_settings(env, "POST", payload)
    assert response.status_code == 200
    assert data["data"]["agents"][0]["__template_key"] == "expert"
    assert env.plugin.spawn_tool is spawn and not spawn.active
    assert spawn.templates[0].agent.instructions == "Find evidence"
    assert spawn.templates[0].agent.tools is None
    assert "researcher" in spawn.description
    assert saved_config["max_steps"] == 17
    persisted = json.loads(
        Path(saved_config.config_path).read_text(encoding="utf-8-sig")
    )
    assert persisted["agents"][0]["name"] == "researcher"
    assert env.runtime._instances[worker.agent_id] is worker

    updated = {"agents": [{"name": "researcher", "enabled": False}]}
    response, _ = await call_settings(env, "POST", updated)
    assert response.status_code == 200 and not spawn.templates
    assert saved_config["agents"][0]["enabled"] is False
    response, _ = await call_settings(env, "POST", {"agents": []})
    assert response.status_code == 200 and saved_config["agents"] == []
    assert env.runtime._instances[worker.agent_id] is worker


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"agents": {}},
        {"agents": [{"name": "INVALID"}]},
        {"agents": [{"name": "same"}, {"name": "same"}]},
        {"agents": [{"name": "expert", "tools": "lookup"}]},
        {"agents": [{"name": "expert", "enabled": "false"}]},
    ],
)
async def test_invalid_expert_settings_do_not_change_configuration(
    environment, saved_config, payload
):
    response, _ = await call_settings(environment, "POST", payload)
    assert response.status_code == 400
    assert saved_config["agents"] == []
    assert not environment.plugin.spawn_tool.templates


@pytest.mark.asyncio
async def test_failed_expert_save_restores_settings_and_templates(
    environment, saved_config, monkeypatch
):
    env = environment
    env.context.persona_manager.get_persona_v3_by_id.return_value = None
    await call_settings(env, "POST", {"agents": [{"name": "original"}]})
    before = dict(saved_config)
    templates = env.plugin.spawn_tool.templates
    orchestrator_templates = env.plugin.orchestrator.templates
    persisted = Path(saved_config.config_path).read_bytes()

    def fail(*_args, **_kwargs):
        raise OSError("Simulated write failure")

    monkeypatch.setattr(AstrBotConfig, "_write_config_snapshot", fail)
    response, _ = await call_settings(
        env, "POST", {"agents": [{"name": "replacement"}]}
    )
    assert response.status_code == 500
    assert dict(saved_config) == before
    assert env.plugin.spawn_tool.templates is templates
    assert env.plugin.orchestrator.templates is orchestrator_templates
    assert Path(saved_config.config_path).read_bytes() == persisted
