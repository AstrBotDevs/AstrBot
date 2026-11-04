import json

from astrbot.core.config.astrbot_config import AstrBotConfig


def test_config_load_preserves_native_subagent_settings(tmp_path):
    """Configuration cleanup stages legacy agents and retains delegation limits."""
    agents = [{"name": "planner", "system_prompt": "Plan the task", "tools": []}]
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
    config = AstrBotConfig(str(config_path))
    assert "subagent_orchestrator" not in config
    pending = config_path.with_suffix(".subagents-migration.json")
    assert json.loads(pending.read_text(encoding="utf-8"))["agents"] == agents
    policy = config["agent"]["config"]["subagents"]
    assert policy["enabled"] is True
    assert policy["max_concurrent_agents"] == 3
    assert len(policy["config_ids"]) == 1
    assert json.loads(config_path.read_text(encoding="utf-8-sig")) == dict(config)
