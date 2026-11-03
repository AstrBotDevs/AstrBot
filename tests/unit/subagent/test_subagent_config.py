import json

from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.config.default import DEFAULT_CONFIG


def test_config_load_preserves_native_subagent_settings(tmp_path):
    """Configuration cleanup retains experts and native delegation limits."""
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
    config = AstrBotConfig(
        str(config_path),
        default_config={
            "subagent_orchestrator": DEFAULT_CONFIG["subagent_orchestrator"]
        },
    )
    assert config["subagent_orchestrator"]["agents"] == agents
    assert config["subagent_orchestrator"]["main_enable"] is True
    assert config["subagent_orchestrator"]["max_concurrent_agents"] == 3
    assert "router_system_prompt" not in config["subagent_orchestrator"]
    assert "remove_main_duplicate_tools" not in config["subagent_orchestrator"]
    assert json.loads(config_path.read_text(encoding="utf-8-sig")) == dict(config)
