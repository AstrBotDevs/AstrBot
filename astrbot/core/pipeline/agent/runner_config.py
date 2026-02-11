from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SUPPORTED_AGENT_RUNNER_TYPES = ("local", "dify", "coze", "dashscope")
AGENT_RUNNER_PROVIDER_KEY = {
    "dify": "dify_agent_runner_provider_id",
    "coze": "coze_agent_runner_provider_id",
    "dashscope": "dashscope_agent_runner_provider_id",
}


def normalize_agent_runner_type(value: object) -> str:
    runner_type = str(value or "local").strip().lower()
    if runner_type in SUPPORTED_AGENT_RUNNER_TYPES:
        return runner_type
    return "local"


def resolve_agent_runner_config(
    node_config: Mapping[str, Any] | None,
) -> tuple[str, str]:
    """Resolve agent runner config from node config only."""
    node = node_config if isinstance(node_config, Mapping) else {}

    runner_type = normalize_agent_runner_type(node.get("agent_runner_type", "local"))
    provider_key = AGENT_RUNNER_PROVIDER_KEY.get(runner_type, "")
    provider_id = str(node.get(provider_key, "") or "").strip() if provider_key else ""

    return runner_type, provider_id
