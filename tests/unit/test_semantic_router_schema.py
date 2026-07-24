import json
from pathlib import Path

from astrbot.core.config.astrbot_config import AstrBotConfig


def test_semantic_router_schema_builds_default_config() -> None:
    """Ensure every object schema has the children AstrBot expects at runtime."""

    schema_path = (
        Path(__file__).resolve().parents[2]
        / "data/plugins/astrbot_plugin_semantic_router/_conf_schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    defaults = AstrBotConfig._config_schema_to_default_config(object(), schema)
    assert defaults["custom_intent_routes"] == []
    assert defaults["control_plane_enabled"] is True
    assert defaults["semantic_planner_enabled"] is True
    assert defaults["context_on_wake_required"] is True
