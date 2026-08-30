from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any

from astrbot.core.config.agent_runner import (
    AGENT_RUNNER_TYPES,
    THIRD_PARTY_AGENT_RUNNER_TYPES,
    get_agent_runner_config_default,
    normalize_agent_runner,
)
from astrbot.core.utils.astrbot_path import (
    get_astrbot_config_path,
    get_astrbot_data_path,
)

logger = logging.getLogger("astrbot")

_LEGACY_AGENT_RUNNER_PROVIDER_ID_KEYS = {
    "dify": "dify_agent_runner_provider_id",
    "coze": "coze_agent_runner_provider_id",
    "dashscope": "dashscope_agent_runner_provider_id",
    "deerflow": "deerflow_agent_runner_provider_id",
}
_LEGACY_AGENT_RUNNER_SETTING_KEYS = (
    "agent_runner_type",
    *_LEGACY_AGENT_RUNNER_PROVIDER_ID_KEYS.values(),
    "default_provider_id",
    "fallback_chat_models",
    "request_max_retries",
    "default_personality",
    "llm_safety_mode",
    "safety_mode_strategy",
    "max_agent_step",
    "tool_schema_mode",
    "tool_call_timeout",
    "sanitize_context_by_modalities",
    "context_limit_reached_strategy",
    "llm_compress_instruction",
    "llm_compress_keep_recent_ratio",
    "llm_compress_provider_id",
    "max_context_length",
    "dequeue_context_length",
    "fallback_max_context_tokens",
)
_LEGACY_PROVIDER_IDENTITY_FIELDS = {
    "id",
    "type",
    "provider",
    "provider_type",
    "enable",
    "provider_source_id",
    "model_config",
}


def _get_effective_provider_map(config: object) -> dict[str, dict[str, Any]]:
    """Build providers with their Provider Source fields merged in.

    Args:
        config: Configuration containing provider and provider_sources lists.

    Returns:
        Effective providers indexed by provider ID.
    """
    if not isinstance(config, dict):
        return {}
    provider_sources = config.get("provider_sources", [])
    source_map = {
        source.get("id"): source
        for source in provider_sources
        if isinstance(source, dict) and source.get("id")
    }
    provider_map: dict[str, dict[str, Any]] = {}
    for provider in config.get("provider", []):
        if not isinstance(provider, dict) or not provider.get("id"):
            continue
        effective_provider = copy.deepcopy(
            source_map.get(provider.get("provider_source_id"), {})
        )
        effective_provider.update(copy.deepcopy(provider))
        provider_map[provider["id"]] = effective_provider
    return provider_map


def _get_provider_runner_type(provider: object) -> str | None:
    """Return the third-party runner type represented by a provider.

    Args:
        provider: Effective provider configuration.

    Returns:
        Runner type when the provider is a known Agent Runner, otherwise None.
    """
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
) -> dict[str, Any]:
    """Copy an effective legacy provider into an inline runner configuration.

    Args:
        runner_type: Destination Agent Runner type.
        provider: Effective provider configuration.

    Returns:
        Normalized inline runner configuration.
    """
    runner_config = {
        key: copy.deepcopy(value)
        for key, value in provider.items()
        if key not in _LEGACY_PROVIDER_IDENTITY_FIELDS
    }
    if not runner_config.get("proxy"):
        proxy_url = provider.get("proxy_url")
        if isinstance(proxy_url, str) and proxy_url:
            runner_config["proxy"] = proxy_url
    return normalize_agent_runner(
        {"runner_type": runner_type, "config": runner_config}
    )["config"]


def _migrate_agent_runner_config(
    config: dict[str, Any],
    fallback_config: dict[str, Any] | None = None,
) -> bool:
    """Migrate legacy Agent Runner fields in one core configuration.

    Args:
        config: Mutable AstrBot configuration loaded from disk.
        fallback_config: Default configuration used to resolve shared providers.

    Returns:
        Whether the configuration changed.
    """
    changed = False
    provider_settings = config.get("provider_settings")
    if not isinstance(provider_settings, dict):
        provider_settings = {}
        config["provider_settings"] = provider_settings
        changed = True

    existing_agent_runner = config.get("agent_runner")
    config_version = config.get("config_version")
    legacy_version = not isinstance(config_version, int) or config_version < 3
    default_local_agent_runner = {
        "runner_type": "local",
        "config": get_agent_runner_config_default("local"),
    }
    default_root_inserted_before_migration = (
        legacy_version
        and existing_agent_runner == default_local_agent_runner
        and any(key in provider_settings for key in _LEGACY_AGENT_RUNNER_SETTING_KEYS)
    )

    if isinstance(existing_agent_runner, dict) and not (
        default_root_inserted_before_migration
    ):
        for key in _LEGACY_AGENT_RUNNER_SETTING_KEYS:
            if key in provider_settings:
                provider_settings.pop(key)
                changed = True
    else:
        provider_map = _get_effective_provider_map(fallback_config)
        provider_map.update(_get_effective_provider_map(config))

        runner_type = provider_settings.get("agent_runner_type", "local")
        if runner_type not in AGENT_RUNNER_TYPES:
            runner_type = "local"
        default_provider_id = provider_settings.get("default_provider_id", "")
        if not isinstance(default_provider_id, str):
            default_provider_id = ""
        default_provider = provider_map.get(default_provider_id)
        default_provider_runner_type = _get_provider_runner_type(default_provider)
        if runner_type == "local" and default_provider_runner_type:
            runner_type = default_provider_runner_type

        if runner_type == "local":
            persona_id = provider_settings.get("default_personality", "default")
            if not isinstance(persona_id, str) or not persona_id:
                persona_id = "default"
            runner_config = get_agent_runner_config_default("local")
            runner_config["model"] = {
                "provider_id": default_provider_id,
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
            runner_config["compression"] = {
                "max_turns": provider_settings.get("max_context_length", -1),
                "trim_turns": provider_settings.get("dequeue_context_length", 1),
                "overflow_strategy": provider_settings.get(
                    "context_limit_reached_strategy", "llm_compress"
                ),
                "instruction": provider_settings.get("llm_compress_instruction", ""),
                "keep_recent_ratio": provider_settings.get(
                    "llm_compress_keep_recent_ratio", 0.15
                ),
                "provider_id": provider_settings.get("llm_compress_provider_id", ""),
                "fallback_max_tokens": provider_settings.get(
                    "fallback_max_context_tokens", 128000
                ),
            }
            runner_config["misc"] = {
                "max_steps": provider_settings.get("max_agent_step", 30),
                "tool_schema_mode": provider_settings.get("tool_schema_mode", "full"),
                "tool_call_timeout": provider_settings.get("tool_call_timeout", 120),
                "sanitize_context_by_modalities": provider_settings.get(
                    "sanitize_context_by_modalities", False
                ),
            }
            runner_config = normalize_agent_runner(
                {"runner_type": "local", "config": runner_config}
            )["config"]
            available_model_provider_ids = {
                provider_id
                for provider_id, provider in provider_map.items()
                if provider.get("provider_type") != "agent_runner"
                and _get_provider_runner_type(provider) is None
            }
            if (
                runner_config["model"]["provider_id"]
                not in available_model_provider_ids
            ):
                runner_config["model"]["provider_id"] = ""
            runner_config["model"]["fallback_provider_ids"] = [
                provider_id
                for provider_id in runner_config["model"]["fallback_provider_ids"]
                if provider_id in available_model_provider_ids
            ]
            if (
                runner_config["compression"]["provider_id"]
                not in available_model_provider_ids
            ):
                runner_config["compression"]["provider_id"] = ""
        else:
            provider_id = provider_settings.get(
                _LEGACY_AGENT_RUNNER_PROVIDER_ID_KEYS[runner_type], ""
            )
            if not provider_id and default_provider_runner_type == runner_type:
                provider_id = default_provider_id
            provider = provider_map.get(provider_id)
            if provider and _get_provider_runner_type(provider) == runner_type:
                runner_config = _copy_provider_config(runner_type, provider)
            else:
                runner_config = get_agent_runner_config_default(runner_type)

        config["agent_runner"] = {
            "runner_type": runner_type,
            "config": runner_config,
        }
        for key in _LEGACY_AGENT_RUNNER_SETTING_KEYS:
            provider_settings.pop(key, None)
        changed = True

    if config.get("config_version") != 3:
        config["config_version"] = 3
        changed = True
    return changed


def migrate_config_on_load(config: dict[str, Any], config_path: Path) -> bool:
    """Run core configuration migrations before integrity cleanup.

    Profile configurations can reference providers stored in the default
    configuration, which has already been loaded and persisted at this point.

    Args:
        config: Mutable AstrBot configuration loaded from disk.
        config_path: Path of the configuration being loaded.

    Returns:
        Whether the configuration changed.
    """
    fallback_config = None
    resolved_path = config_path.resolve()
    profile_root = Path(get_astrbot_config_path()).resolve()
    if resolved_path.is_relative_to(profile_root):
        default_path = Path(get_astrbot_data_path()) / "cmd_config.json"
        try:
            with default_path.open(encoding="utf-8-sig") as default_file:
                loaded_default = json.load(default_file)
            if isinstance(loaded_default, dict):
                fallback_config = loaded_default
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Failed to load default configuration while migrating %s: %s",
                resolved_path,
                exc,
            )
    return _migrate_agent_runner_config(config, fallback_config)


def finalize_config_migrations(configs: list[dict[str, Any]]) -> bool:
    """Clean legacy shared data after every profile has been migrated.

    Args:
        configs: Loaded configurations with the default configuration first.

    Returns:
        Whether the default configuration changed.
    """
    if not configs:
        return False
    default_config = configs[0]
    providers = default_config.get("provider", [])
    if not isinstance(providers, list):
        return False
    effective_provider_map = _get_effective_provider_map(default_config)
    filtered_providers = [
        provider
        for provider in providers
        if not (
            isinstance(provider, dict)
            and (
                provider.get("provider_type") == "agent_runner"
                or effective_provider_map.get(provider.get("id"), {}).get(
                    "provider_type"
                )
                == "agent_runner"
                or _get_provider_runner_type(
                    effective_provider_map.get(provider.get("id"), provider)
                )
                is not None
            )
        )
    ]
    if len(filtered_providers) == len(providers):
        return False
    default_config["provider"] = filtered_providers
    return True
