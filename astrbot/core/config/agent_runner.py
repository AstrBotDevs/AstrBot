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
        "misc": {
            "max_steps": 30,
            "tool_schema_mode": "full",
            "overflow_strategy": "llm_compress",
            "compress_instruction": "",
            "compress_keep_recent_ratio": 0.15,
            "compress_provider_id": "",
            "max_turns": -1,
            "trim_turns": 1,
            "fallback_max_tokens": 128000,
        },
    },
    "dify": {
        "persona_id": "default",
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
        "persona_id": "default",
        "coze_api_key": "",
        "bot_id": "",
        "coze_api_base": "https://api.coze.cn",
        "auto_save_history": True,
        "timeout": 60,
        "proxy": "",
    },
    "dashscope": {
        "persona_id": "default",
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
        "persona_id": "default",
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

LEGACY_AGENT_RUNNER_PROVIDER_ID_KEYS = {
    "dify": "dify_agent_runner_provider_id",
    "coze": "coze_agent_runner_provider_id",
    "dashscope": "dashscope_agent_runner_provider_id",
    "deerflow": "deerflow_agent_runner_provider_id",
}

_LEGACY_PROVIDER_ID_MARKER = "_legacy_provider_id"
_LEGACY_DEFAULT_PROVIDER_ID_MARKER = "_legacy_default_provider_id"
_LEGACY_LOCAL_REFERENCES_MARKER = "_legacy_local_references"
_LEGACY_PROVIDER_IDENTITY_FIELDS = {
    "id",
    "type",
    "provider",
    "provider_type",
    "enable",
    "provider_source_id",
    "model_config",
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
        except (TypeError, ValueError):
            return default
    if isinstance(default, float):
        if isinstance(value, bool):
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
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
        ratio = normalized["misc"]["compress_keep_recent_ratio"]
        normalized["misc"]["compress_keep_recent_ratio"] = min(0.3, max(0.0, ratio))
        if normalized["model"]["request_max_retries"] < 1:
            normalized["model"]["request_max_retries"] = 1
        if normalized["misc"]["max_steps"] < 1:
            normalized["misc"]["max_steps"] = 1
        if normalized["misc"]["trim_turns"] < 1:
            normalized["misc"]["trim_turns"] = 1
    return {"runner_type": runner_type, "config": normalized}


def _get_provider_runner_type(provider: object) -> str | None:
    if not isinstance(provider, dict):
        return None
    provider_type = provider.get("provider_type")
    runner_type = provider.get("type") or provider.get("provider")
    if (
        provider_type == "agent_runner"
        and runner_type in THIRD_PARTY_AGENT_RUNNER_TYPES
    ):
        return runner_type
    expected_field = {
        "dify": "dify_api_key",
        "coze": "coze_api_key",
        "dashscope": "dashscope_app_id",
        "deerflow": "deerflow_api_base",
    }
    if (
        runner_type in THIRD_PARTY_AGENT_RUNNER_TYPES
        and expected_field[runner_type] in provider
    ):
        return runner_type
    return None


def _copy_provider_config(
    runner_type: str,
    provider: dict[str, Any],
    persona_id: str,
) -> dict[str, Any]:
    config = {
        key: copy.deepcopy(value)
        for key, value in provider.items()
        if key not in _LEGACY_PROVIDER_IDENTITY_FIELDS
    }
    config["persona_id"] = persona_id
    return normalize_agent_runner({"runner_type": runner_type, "config": config})[
        "config"
    ]


def prepare_agent_runner_migration(config: dict[str, Any]) -> bool:
    """Move legacy runner fields before generic integrity cleanup runs.

    Provider references that cannot be resolved from the current file are retained
    as private migration markers until all profiles and the global provider catalog
    have been loaded.

    Args:
        config: Mutable AstrBot configuration loaded from disk.

    Returns:
        Whether the configuration was changed.
    """
    changed = False
    provider_settings = config.get("provider_settings")
    if not isinstance(provider_settings, dict):
        provider_settings = {}
        config["provider_settings"] = provider_settings
        changed = True

    if isinstance(config.get("agent_runner"), dict):
        for key in (
            "agent_runner_type",
            *LEGACY_AGENT_RUNNER_PROVIDER_ID_KEYS.values(),
            "default_provider_id",
            "fallback_chat_models",
            "request_max_retries",
            "default_personality",
            "llm_safety_mode",
            "safety_mode_strategy",
            "max_agent_step",
            "tool_schema_mode",
            "context_limit_reached_strategy",
            "llm_compress_instruction",
            "llm_compress_keep_recent_ratio",
            "llm_compress_provider_id",
            "max_context_length",
            "dequeue_context_length",
            "fallback_max_context_tokens",
        ):
            if key in provider_settings:
                provider_settings.pop(key)
                changed = True
    else:
        runner_type = provider_settings.get("agent_runner_type", "local")
        if runner_type not in AGENT_RUNNER_TYPES:
            runner_type = "local"
        persona_id = provider_settings.get("default_personality", "default")
        if not isinstance(persona_id, str) or not persona_id:
            persona_id = "default"

        providers = config.get("provider", [])
        provider_map = {
            provider.get("id"): provider
            for provider in providers
            if isinstance(provider, dict) and provider.get("id")
        }
        default_provider_id = provider_settings.get("default_provider_id", "")
        default_provider = provider_map.get(default_provider_id)
        default_provider_runner_type = _get_provider_runner_type(default_provider)
        if runner_type == "local" and default_provider_runner_type:
            runner_type = default_provider_runner_type

        if runner_type == "local":
            runner_config = get_agent_runner_config_default("local")
            runner_config["model"] = {
                "provider_id": default_provider_id
                if isinstance(default_provider_id, str)
                else "",
                "fallback_provider_ids": copy.deepcopy(
                    provider_settings.get("fallback_chat_models", [])
                ),
                "request_max_retries": provider_settings.get("request_max_retries", 5),
            }
            runner_config["persona"] = {
                "persona_id": persona_id,
                "safety_mode": provider_settings.get("llm_safety_mode", True),
                "safety_mode_strategy": provider_settings.get(
                    "safety_mode_strategy", "system_prompt"
                ),
            }
            runner_config["misc"] = {
                "max_steps": provider_settings.get("max_agent_step", 30),
                "tool_schema_mode": provider_settings.get("tool_schema_mode", "full"),
                "overflow_strategy": provider_settings.get(
                    "context_limit_reached_strategy", "llm_compress"
                ),
                "compress_instruction": provider_settings.get(
                    "llm_compress_instruction", ""
                ),
                "compress_keep_recent_ratio": provider_settings.get(
                    "llm_compress_keep_recent_ratio", 0.15
                ),
                "compress_provider_id": provider_settings.get(
                    "llm_compress_provider_id", ""
                ),
                "max_turns": provider_settings.get("max_context_length", -1),
                "trim_turns": provider_settings.get("dequeue_context_length", 1),
                "fallback_max_tokens": provider_settings.get(
                    "fallback_max_context_tokens", 128000
                ),
            }
            runner_config = normalize_agent_runner(
                {"runner_type": "local", "config": runner_config}
            )["config"]
            runner_config[_LEGACY_LOCAL_REFERENCES_MARKER] = True
            if default_provider_id and not default_provider:
                runner_config[_LEGACY_DEFAULT_PROVIDER_ID_MARKER] = default_provider_id
        else:
            provider_id = provider_settings.get(
                LEGACY_AGENT_RUNNER_PROVIDER_ID_KEYS[runner_type], ""
            )
            if not provider_id and default_provider_runner_type == runner_type:
                provider_id = default_provider_id
            provider = provider_map.get(provider_id)
            if provider and _get_provider_runner_type(provider) == runner_type:
                runner_config = _copy_provider_config(runner_type, provider, persona_id)
            else:
                runner_config = get_agent_runner_config_default(runner_type)
                runner_config["persona_id"] = persona_id
                if provider_id:
                    runner_config[_LEGACY_PROVIDER_ID_MARKER] = provider_id

        config["agent_runner"] = {
            "runner_type": runner_type,
            "config": runner_config,
        }
        for key in (
            "agent_runner_type",
            *LEGACY_AGENT_RUNNER_PROVIDER_ID_KEYS.values(),
            "default_provider_id",
            "fallback_chat_models",
            "request_max_retries",
            "default_personality",
            "llm_safety_mode",
            "safety_mode_strategy",
            "max_agent_step",
            "tool_schema_mode",
            "context_limit_reached_strategy",
            "llm_compress_instruction",
            "llm_compress_keep_recent_ratio",
            "llm_compress_provider_id",
            "max_context_length",
            "dequeue_context_length",
            "fallback_max_context_tokens",
        ):
            provider_settings.pop(key, None)
        changed = True

    if config.get("config_version") != 3:
        config["config_version"] = 3
        changed = True
    return changed


def finalize_agent_runner_migration(configs: list[dict[str, Any]]) -> bool:
    """Resolve deferred provider references and remove legacy runner providers.

    Args:
        configs: Loaded configurations with the global configuration first.

    Returns:
        Whether any configuration changed.
    """
    if not configs:
        return False
    global_config = configs[0]
    providers = global_config.get("provider", [])
    provider_map = {
        provider.get("id"): provider
        for provider in providers
        if isinstance(provider, dict) and provider.get("id")
    }
    changed = False

    for config in configs:
        agent_runner = config.get("agent_runner")
        if not isinstance(agent_runner, dict):
            continue
        runner_type = agent_runner.get("runner_type")
        runner_config = agent_runner.get("config")
        if runner_type not in AGENT_RUNNER_TYPES or not isinstance(runner_config, dict):
            config["agent_runner"] = normalize_agent_runner(agent_runner)
            changed = True
            continue

        provider_id = runner_config.pop(_LEGACY_PROVIDER_ID_MARKER, "")
        default_provider_id = runner_config.pop(_LEGACY_DEFAULT_PROVIDER_ID_MARKER, "")
        legacy_local_references = runner_config.pop(
            _LEGACY_LOCAL_REFERENCES_MARKER, False
        )
        if legacy_local_references:
            changed = True
        if provider_id:
            provider = provider_map.get(provider_id)
            persona_id = runner_config.get("persona_id", "default")
            if provider and _get_provider_runner_type(provider) == runner_type:
                agent_runner["config"] = _copy_provider_config(
                    runner_type, provider, persona_id
                )
            else:
                agent_runner["config"] = get_agent_runner_config_default(runner_type)
                agent_runner["config"]["persona_id"] = persona_id
            changed = True
        elif default_provider_id:
            provider = provider_map.get(default_provider_id)
            provider_runner_type = _get_provider_runner_type(provider)
            if provider and provider_runner_type:
                persona_id = runner_config.get("persona", {}).get(
                    "persona_id", "default"
                )
                config["agent_runner"] = {
                    "runner_type": provider_runner_type,
                    "config": _copy_provider_config(
                        provider_runner_type, provider, persona_id
                    ),
                }
            changed = True

        migrated_agent_runner = config["agent_runner"]
        if legacy_local_references and migrated_agent_runner["runner_type"] == "local":
            migrated_config = migrated_agent_runner["config"]
            model_config = migrated_config["model"]
            available_model_provider_ids = {
                provider_id
                for provider_id, provider in provider_map.items()
                if provider.get("provider_type") != "agent_runner"
                and _get_provider_runner_type(provider) is None
            }
            current_provider_id = model_config["provider_id"]
            if (
                current_provider_id
                and current_provider_id not in available_model_provider_ids
            ):
                model_config["provider_id"] = ""
            model_config["fallback_provider_ids"] = [
                fallback_id
                for fallback_id in model_config["fallback_provider_ids"]
                if fallback_id in available_model_provider_ids
            ]
            compress_provider_id = migrated_config["misc"]["compress_provider_id"]
            if (
                compress_provider_id
                and compress_provider_id not in available_model_provider_ids
            ):
                migrated_config["misc"]["compress_provider_id"] = ""

    filtered_providers = [
        provider
        for provider in providers
        if not (
            isinstance(provider, dict)
            and (
                provider.get("provider_type") == "agent_runner"
                or _get_provider_runner_type(provider) is not None
            )
        )
    ]
    if len(filtered_providers) != len(providers):
        global_config["provider"] = filtered_providers
        changed = True
    return changed
