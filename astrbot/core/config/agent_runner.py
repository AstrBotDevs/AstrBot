from __future__ import annotations

import copy
from typing import Any

AGENT_RUNNER_TYPES = ("local", "dify", "coze", "dashscope", "deerflow")
THIRD_PARTY_AGENT_RUNNER_TYPES = AGENT_RUNNER_TYPES[1:]

AGENT_RUNNER_CONFIG_DEFAULTS: dict[str, dict[str, Any]] = {
    "local": {
        "model": {
            "provider_id": "",
            "fallback_provider_ids": [],
            "request_max_retries": 5,
        },
        "persona": {
            "persona_id": "default",
            "safety_mode": True,
            "safety_mode_strategy": "system_prompt",
        },
        "compression": {
            "max_turns": -1,
            "trim_turns": 1,
            "overflow_strategy": "llm_compress",
            "instruction": "",
            "keep_recent_ratio": 0.15,
            "provider_id": "",
            "fallback_max_tokens": 128000,
        },
        "misc": {
            "max_steps": 30,
            "tool_schema_mode": "full",
            "tool_call_timeout": 120,
            "sanitize_context_by_modalities": False,
        },
    },
    "dify": {
        "dify_api_type": "chat",
        "dify_api_key": "",
        "dify_api_base": "https://api.dify.ai/v1",
        "dify_workflow_output_key": "astrbot_wf_output",
        "dify_query_input_key": "astrbot_text_query",
        "variables": {},
        "timeout": 60,
        "proxy": "",
    },
    "coze": {
        "coze_api_key": "",
        "bot_id": "",
        "coze_api_base": "https://api.coze.cn",
        "auto_save_history": True,
        "timeout": 60,
        "proxy": "",
    },
    "dashscope": {
        "dashscope_app_type": "agent",
        "dashscope_api_key": "",
        "dashscope_app_id": "",
        "rag_options": {
            "pipeline_ids": [],
            "file_ids": [],
            "output_reference": False,
        },
        "variables": {},
        "timeout": 60,
        "proxy": "",
    },
    "deerflow": {
        "deerflow_api_base": "http://127.0.0.1:2026",
        "deerflow_api_key": "",
        "deerflow_auth_header": "",
        "deerflow_assistant_id": "lead_agent",
        "deerflow_model_name": "",
        "deerflow_thinking_enabled": False,
        "deerflow_plan_mode": False,
        "deerflow_subagent_enabled": False,
        "deerflow_max_concurrent_subagents": 3,
        "deerflow_recursion_limit": 1000,
        "timeout": 300,
        "proxy": "",
    },
}


def get_agent_runner_config_default(runner_type: str) -> dict[str, Any]:
    """Return an isolated default configuration for an Agent Runner type.

    Args:
        runner_type: Short runner type name.

    Returns:
        A deep copy of the runner configuration defaults.

    Raises:
        ValueError: If the runner type is unsupported.
    """
    if runner_type not in AGENT_RUNNER_CONFIG_DEFAULTS:
        raise ValueError(f"Unsupported Agent Runner type: {runner_type}")
    return copy.deepcopy(AGENT_RUNNER_CONFIG_DEFAULTS[runner_type])


def _normalize_value(value: Any, default: Any) -> Any:
    if isinstance(default, dict):
        if not isinstance(value, dict):
            return copy.deepcopy(default)
        if not default:
            return copy.deepcopy(value)
        return {
            key: _normalize_value(value.get(key), child_default)
            for key, child_default in default.items()
        }
    if isinstance(default, list):
        return (
            copy.deepcopy(value) if isinstance(value, list) else copy.deepcopy(default)
        )
    if isinstance(default, bool):
        return value if isinstance(value, bool) else default
    if isinstance(default, int):
        if isinstance(value, bool):
            return default
        try:
            return int(value)
        except TypeError, ValueError:
            return default
    if isinstance(default, float):
        if isinstance(value, bool):
            return default
        try:
            return float(value)
        except TypeError, ValueError:
            return default
    if isinstance(default, str):
        return value if isinstance(value, str) else default
    return copy.deepcopy(value) if value is not None else copy.deepcopy(default)


def normalize_agent_runner(agent_runner: object) -> dict[str, Any]:
    """Validate and normalize a complete Agent Runner configuration.

    Args:
        agent_runner: Untrusted root Agent Runner configuration.

    Returns:
        A normalized configuration containing only fields for the selected runner.

    Raises:
        ValueError: If the root value or runner type is invalid.
    """
    if not isinstance(agent_runner, dict):
        raise ValueError("agent_runner must be an object")
    runner_type = agent_runner.get("runner_type")
    if runner_type not in AGENT_RUNNER_TYPES:
        raise ValueError(f"Unsupported Agent Runner type: {runner_type}")
    config = agent_runner.get("config", {})
    default = AGENT_RUNNER_CONFIG_DEFAULTS[runner_type]
    normalized = _normalize_value(config, default)
    if runner_type == "local":
        ratio = normalized["compression"]["keep_recent_ratio"]
        normalized["compression"]["keep_recent_ratio"] = min(0.3, max(0.0, ratio))
        if normalized["model"]["request_max_retries"] < 1:
            normalized["model"]["request_max_retries"] = 1
        if normalized["misc"]["max_steps"] < 1:
            normalized["misc"]["max_steps"] = 1
        if normalized["compression"]["trim_turns"] < 1:
            normalized["compression"]["trim_turns"] = 1
    return {"runner_type": runner_type, "config": normalized}


def get_persona_id(agent_runner: object, default: str = "default") -> str:
    """Return the configured persona id for a normalized Agent Runner.

    Args:
        agent_runner: Root Agent Runner configuration.
        default: Fallback persona id.

    Returns:
        Persona id from the local runner, or ``default`` otherwise.
    """
    if not isinstance(agent_runner, dict):
        return default
    runner_config = agent_runner.get("config", {})
    if not isinstance(runner_config, dict):
        return default
    if agent_runner.get("runner_type") == "local":
        persona = runner_config.get("persona", {})
        persona_id = (
            persona.get("persona_id", default) if isinstance(persona, dict) else default
        )
    else:
        persona_id = runner_config.get("persona_id", default)
    return persona_id if isinstance(persona_id, str) and persona_id else default
