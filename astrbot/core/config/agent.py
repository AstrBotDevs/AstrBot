"""Inline AgentConfig defaults and legacy execution-path configuration."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from astrbot.core.agent.config import AgentConfig

from .agent_runner import get_agent_runner_config_default, normalize_agent_runner

AGENT_RUNTIME_TYPES = ("astrbot", "dify", "coze", "dashscope", "deerflow")


def get_runtime_config_default(
    runtime: str, *, delegated: bool = False
) -> dict[str, Any]:
    """Return defaults for an inline or stored runtime configuration.

    Args:
        runtime: Built-in runtime or existing third-party execution path.
        delegated: Whether to return only reusable persona/model overrides.

    Returns:
        Independent configuration defaults.
    """
    if runtime == "astrbot" and delegated:
        return {"model": {"provider_id": ""}, "persona": {"persona_id": ""}}
    config = get_agent_runner_config_default(
        "local" if runtime == "astrbot" else runtime
    )
    if runtime == "astrbot":
        config["persona"].update(system_prompt="", tools=None, skills=None)
        config["subagents"] = {
            "enabled": False,
            "config_ids": [],
            "max_concurrent_agents": 3,
            "task_timeout": 600,
        }
    return config


def normalize_agent(value: object, *, delegated: bool = False) -> dict[str, Any]:
    """Validate a configuration without discarding configuration of external runtimes.

    Args:
        value: Untrusted runtime selection and configuration.
        delegated: Whether to retain only optional persona/model overrides.

    Returns:
        Validated agent_config with defaults for known execution paths.

    Raises:
        ValueError: If the agent_config or native options are invalid.
    """
    agent_config = AgentConfig.model_validate(value)
    if agent_config.runtime not in AGENT_RUNTIME_TYPES:
        return agent_config.model_dump()
    source: dict[str, Any] = agent_config.model_dump()["config"]
    if agent_config.runtime == "astrbot" and delegated:
        overrides = {}
        for section, key in (("model", "provider_id"), ("persona", "persona_id")):
            values = source.get(section, {})
            if not isinstance(values, dict):
                raise ValueError(f"agent.config.{section} must be an object")
            selected_id = values.get(key, "")
            if selected_id is None:
                selected_id = ""
            if not isinstance(selected_id, str):
                raise ValueError(f"agent.config.{section}.{key} must be a string")
            overrides[section] = {key: selected_id.strip()}
        return {"runtime": "astrbot", "config": overrides}
    config = normalize_agent_runner(
        {
            "runner_type": "local"
            if agent_config.runtime == "astrbot"
            else agent_config.runtime,
            "config": source,
        }
    )["config"]
    if agent_config.runtime == "astrbot":
        defaults = get_runtime_config_default("astrbot", delegated=delegated)
        persona = source.get("persona", {})
        if not isinstance(persona, dict):
            raise ValueError("agent.config.persona must be an object")
        for key in ("system_prompt", "tools", "skills"):
            config["persona"][key] = deepcopy(
                persona.get(key, defaults["persona"][key])
            )
        delegation = source.get("subagents", {})
        if not isinstance(delegation, dict):
            raise ValueError("agent.config.subagents must be an object")
        selection = delegation.get("config_ids", [])
        if not isinstance(selection, list) or any(
            not isinstance(item, str) or not item.strip() for item in selection
        ):
            raise ValueError("subagents.config_ids must be an array of nonempty IDs")
        if not isinstance(delegation.get("enabled", False), bool):
            raise ValueError("subagents.enabled must be a boolean")
        for key, default in (("max_concurrent_agents", 3), ("task_timeout", 600)):
            limit = delegation.get(key, default)
            if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
                raise ValueError(f"subagents.{key} must be a positive integer")
        config["subagents"] = {
            "enabled": delegation.get("enabled", False),
            "config_ids": list(dict.fromkeys(selection)),
            "max_concurrent_agents": max(
                1, int(delegation.get("max_concurrent_agents", 3))
            ),
            "task_timeout": max(1, int(delegation.get("task_timeout", 600))),
        }
        for key in ("tools", "skills"):
            selected = config["persona"][key]
            if selected is not None and (
                not isinstance(selected, list)
                or any(not isinstance(item, str) for item in selected)
            ):
                raise ValueError(f"persona.{key} must be null or an array of names")
        if not isinstance(config["persona"]["system_prompt"], str):
            raise ValueError("persona.system_prompt must be text")
    return {"runtime": agent_config.runtime, "config": config}
