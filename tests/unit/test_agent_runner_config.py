import copy
import json

import pytest

from astrbot.core.config.agent_runner import (
    AGENT_RUNNER_CONFIG_DEFAULTS,
    finalize_agent_runner_migration,
    get_agent_runner_config_default,
    normalize_agent_runner,
    prepare_agent_runner_migration,
)
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.config.default import DEFAULT_CONFIG


@pytest.mark.parametrize(
    "runner_type", ["local", "dify", "coze", "dashscope", "deerflow"]
)
def test_agent_runner_defaults_are_isolated_and_normalized(runner_type: str):
    first = get_agent_runner_config_default(runner_type)
    second = get_agent_runner_config_default(runner_type)

    first["test_mutation"] = True

    assert second == AGENT_RUNNER_CONFIG_DEFAULTS[runner_type]
    assert normalize_agent_runner({"runner_type": runner_type, "config": second}) == {
        "runner_type": runner_type,
        "config": second,
    }
    if runner_type != "local":
        assert "persona_id" not in second


def test_switching_runner_type_discards_previous_runner_fields():
    normalized = normalize_agent_runner(
        {
            "runner_type": "dify",
            "config": {
                "provider_id": "legacy-provider",
                "persona_id": "legacy-persona",
                "model": {"provider_id": "chat-model"},
                "dify_api_key": "secret",
                "unexpected": True,
            },
        }
    )

    assert normalized["config"] == {
        **get_agent_runner_config_default("dify"),
        "dify_api_key": "secret",
    }
    assert "provider_id" not in normalized["config"]
    assert "persona_id" not in normalized["config"]
    assert "model" not in normalized["config"]


@pytest.mark.parametrize(
    "runner_type", ["local", "dify", "coze", "dashscope", "deerflow"]
)
def test_each_runner_configuration_round_trips(tmp_path, runner_type: str):
    config = copy.deepcopy(DEFAULT_CONFIG)
    expected = {
        "runner_type": runner_type,
        "config": get_agent_runner_config_default(runner_type),
    }
    config["agent_runner"] = expected
    config_path = tmp_path / f"{runner_type}.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    loaded = AstrBotConfig(config_path=str(config_path))
    loaded.save_config()
    reloaded = AstrBotConfig(config_path=str(config_path))

    assert reloaded["agent_runner"] == expected


def test_local_legacy_fields_are_fully_migrated():
    config = {
        "config_version": 2,
        "provider": [],
        "provider_settings": {
            "agent_runner_type": "local",
            "default_provider_id": "chat-main",
            "fallback_chat_models": ["chat-backup"],
            "request_max_retries": 7,
            "default_personality": "developer",
            "llm_safety_mode": False,
            "safety_mode_strategy": "system_prompt",
            "max_agent_step": 42,
            "tool_schema_mode": "skills_like",
            "context_limit_reached_strategy": "truncate_by_turns",
            "llm_compress_instruction": "Summarize",
            "llm_compress_keep_recent_ratio": 0.2,
            "llm_compress_provider_id": "compressor",
            "max_context_length": 20,
            "dequeue_context_length": 3,
            "fallback_max_context_tokens": 64000,
        },
    }

    assert prepare_agent_runner_migration(config)
    finalize_agent_runner_migration(
        [
            {
                "provider": [
                    {"id": "chat-main", "provider_type": "chat_completion"},
                    {"id": "chat-backup", "provider_type": "chat_completion"},
                    {"id": "compressor", "provider_type": "chat_completion"},
                ]
            },
            config,
        ]
    )
    assert config["config_version"] == 3
    assert config["agent_runner"] == {
        "runner_type": "local",
        "config": {
            "model": {
                "provider_id": "chat-main",
                "fallback_provider_ids": ["chat-backup"],
                "request_max_retries": 7,
            },
            "persona": {
                "persona_id": "developer",
                "safety_mode": False,
                "safety_mode_strategy": "system_prompt",
            },
            "misc": {
                "max_steps": 42,
                "tool_schema_mode": "skills_like",
                "overflow_strategy": "truncate_by_turns",
                "compress_instruction": "Summarize",
                "compress_keep_recent_ratio": 0.2,
                "compress_provider_id": "compressor",
                "max_turns": 20,
                "trim_turns": 3,
                "fallback_max_tokens": 64000,
            },
        },
    }
    assert not {
        "agent_runner_type",
        "default_provider_id",
        "fallback_chat_models",
        "request_max_retries",
        "default_personality",
        "max_agent_step",
    }.intersection(config["provider_settings"])


def test_missing_local_provider_references_are_removed():
    config = {
        "provider": [],
        "provider_settings": {
            "agent_runner_type": "local",
            "default_provider_id": "missing-main",
            "fallback_chat_models": ["available", "missing-fallback"],
            "llm_compress_provider_id": "missing-compressor",
        },
    }
    global_config = {
        "provider": [{"id": "available", "provider_type": "chat_completion"}]
    }

    prepare_agent_runner_migration(config)
    finalize_agent_runner_migration([global_config, config])

    runner_config = config["agent_runner"]["config"]
    assert runner_config["model"]["provider_id"] == ""
    assert runner_config["model"]["fallback_provider_ids"] == ["available"]
    assert runner_config["misc"]["compress_provider_id"] == ""


@pytest.mark.parametrize(
    ("runner_type", "provider_config", "expected_key"),
    [
        (
            "dify",
            {"dify_api_key": "dify-key", "dify_api_type": "workflow"},
            "dify_api_key",
        ),
        (
            "coze",
            {"coze_api_key": "coze-key", "bot_id": "bot"},
            "coze_api_key",
        ),
        (
            "dashscope",
            {"dashscope_api_key": "dash-key", "dashscope_app_id": "app"},
            "dashscope_api_key",
        ),
        (
            "deerflow",
            {"deerflow_api_key": "deer-key", "deerflow_plan_mode": True},
            "deerflow_api_key",
        ),
    ],
)
def test_third_party_provider_config_is_copied_inline(
    runner_type: str,
    provider_config: dict,
    expected_key: str,
):
    provider_id = f"{runner_type}-provider"
    config = {
        "config_version": 2,
        "provider": [],
        "provider_settings": {
            "agent_runner_type": runner_type,
            f"{runner_type}_agent_runner_provider_id": provider_id,
            "default_personality": "operator",
        },
    }
    global_config = {
        "provider": [
            {
                "id": provider_id,
                "type": runner_type,
                "provider": runner_type,
                "provider_type": "agent_runner",
                "enable": True,
                **provider_config,
            }
        ]
    }

    prepare_agent_runner_migration(config)
    assert finalize_agent_runner_migration([global_config, config])

    runner_config = config["agent_runner"]["config"]
    assert config["agent_runner"]["runner_type"] == runner_type
    assert runner_config[expected_key] == provider_config[expected_key]
    assert not {
        "id",
        "type",
        "provider",
        "provider_type",
        "enable",
        "persona_id",
    }.intersection(runner_config)
    assert global_config["provider"] == []


def test_missing_third_party_provider_uses_runner_defaults():
    config = {
        "provider": [],
        "provider_settings": {
            "agent_runner_type": "coze",
            "coze_agent_runner_provider_id": "missing",
            "default_personality": "operator",
        },
    }

    prepare_agent_runner_migration(config)
    finalize_agent_runner_migration([{"provider": []}, config])

    expected = get_agent_runner_config_default("coze")
    assert config["agent_runner"] == {
        "runner_type": "coze",
        "config": expected,
    }


def test_legacy_default_provider_only_selects_actual_third_party_runner():
    chat_config = {
        "provider": [],
        "provider_settings": {
            "agent_runner_type": "local",
            "default_provider_id": "chat-model",
        },
    }
    runner_config = {
        "provider": [],
        "provider_settings": {
            "agent_runner_type": "local",
            "default_provider_id": "dify-provider",
        },
    }
    global_config = {
        "provider": [
            {
                "id": "chat-model",
                "type": "openai_chat_completion",
                "provider_type": "chat_completion",
            },
            {
                "id": "dify-provider",
                "type": "dify",
                "provider_type": "agent_runner",
                "dify_api_key": "secret",
            },
        ]
    }

    prepare_agent_runner_migration(chat_config)
    prepare_agent_runner_migration(runner_config)
    finalize_agent_runner_migration([global_config, chat_config, runner_config])

    assert chat_config["agent_runner"]["runner_type"] == "local"
    assert chat_config["agent_runner"]["config"]["model"]["provider_id"] == "chat-model"
    assert runner_config["agent_runner"]["runner_type"] == "dify"
    assert runner_config["agent_runner"]["config"]["dify_api_key"] == "secret"


def test_multiple_profiles_can_copy_one_provider_and_migration_is_idempotent():
    global_config = {
        "provider": [
            {
                "id": "shared-deerflow",
                "type": "deerflow",
                "provider_type": "agent_runner",
                "deerflow_api_key": "shared-key",
            },
            {
                "id": "unused-coze",
                "type": "coze",
                "provider_type": "agent_runner",
                "coze_api_key": "unused",
            },
            {
                "id": "unused-custom-runner",
                "type": "custom-runner",
                "provider_type": "agent_runner",
            },
        ],
        "provider_settings": {},
        "agent_runner": {
            "runner_type": "local",
            "config": get_agent_runner_config_default("local"),
        },
    }
    profiles = []
    for persona_id in ("one", "two"):
        profile = {
            "provider": [],
            "provider_settings": {
                "agent_runner_type": "deerflow",
                "deerflow_agent_runner_provider_id": "shared-deerflow",
                "default_personality": persona_id,
            },
        }
        prepare_agent_runner_migration(profile)
        profiles.append(profile)

    finalize_agent_runner_migration([global_config, *profiles])
    first_result = copy.deepcopy([global_config, *profiles])

    assert [
        profile["agent_runner"]["config"]["deerflow_api_key"] for profile in profiles
    ] == ["shared-key", "shared-key"]
    assert all(
        "persona_id" not in profile["agent_runner"]["config"] for profile in profiles
    )
    assert global_config["provider"] == []
    assert not finalize_agent_runner_migration([global_config, *profiles])
    assert [global_config, *profiles] == first_result


def test_new_agent_runner_config_is_authoritative_and_opaque_on_reload(tmp_path):
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["provider_settings"]["agent_runner_type"] = "coze"
    config["agent_runner"] = {
        "runner_type": "dify",
        "config": {
            **get_agent_runner_config_default("dify"),
            "dify_api_key": "saved-key",
            "variables": {"nested": {"value": 1}},
        },
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    loaded = AstrBotConfig(config_path=str(config_path))

    assert loaded["agent_runner"]["runner_type"] == "dify"
    assert loaded["agent_runner"]["config"]["dify_api_key"] == "saved-key"
    assert loaded["agent_runner"]["config"]["variables"] == {"nested": {"value": 1}}
    assert "agent_runner_type" not in loaded["provider_settings"]
