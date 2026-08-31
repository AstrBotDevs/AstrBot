import copy
import json

import pytest

from astrbot.core.config.agent_runner import (
    AGENT_RUNNER_CONFIG_DEFAULTS,
    get_agent_runner_config_default,
    get_persona_id,
    normalize_agent_runner,
    normalize_agent_runner_for_load,
)
from astrbot.core.config.agent_runner_migration import (
    _migrate_agent_runner_config,
    finalize_config_migrations,
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
        assert second["persona_id"] == "default"
        assert second["max_steps"] == 30
        assert second["proxy_mode"] == "inherit"
        assert second["proxy_url"] == ""
        assert "proxy" not in second


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
        "persona_id": "legacy-persona",
    }
    assert "provider_id" not in normalized["config"]
    assert "model" not in normalized["config"]


def test_agent_request_normalizes_incomplete_runner_config():
    normalized = normalize_agent_runner(
        {
            "runner_type": "dify",
            "config": {"dify_api_key": "saved-key"},
        }
    )

    assert normalized == {
        "runner_type": "dify",
        "config": {
            **get_agent_runner_config_default("dify"),
            "dify_api_key": "saved-key",
        },
    }


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
            "tool_call_timeout": 88,
            "sanitize_context_by_modalities": True,
            "context_limit_reached_strategy": "truncate_by_turns",
            "llm_compress_instruction": "Summarize",
            "llm_compress_keep_recent_ratio": 0.2,
            "llm_compress_provider_id": "compressor",
            "max_context_length": 20,
            "dequeue_context_length": 3,
            "fallback_max_context_tokens": 64000,
        },
    }

    default_config = {
        "provider": [
            {"id": "chat-main", "provider_type": "chat_completion"},
            {"id": "chat-backup", "provider_type": "chat_completion"},
            {"id": "compressor", "provider_type": "chat_completion"},
        ]
    }
    assert _migrate_agent_runner_config(config, default_config)
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
            "compression": {
                "max_turns": 20,
                "trim_turns": 3,
                "overflow_strategy": "truncate_by_turns",
                "instruction": "Summarize",
                "keep_recent_ratio": 0.2,
                "provider_id": "compressor",
                "fallback_max_tokens": 64000,
            },
            "misc": {
                "max_steps": 42,
                "tool_schema_mode": "skills_like",
                "tool_call_timeout": 88,
                "sanitize_context_by_modalities": True,
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
        "tool_call_timeout",
        "sanitize_context_by_modalities",
    }.intersection(config["provider_settings"])


def test_local_migration_replaces_default_root_inserted_before_version_bump():
    config = {
        "config_version": 2,
        "provider": [
            {"id": "chat-main", "provider_type": "chat_completion"},
            {"id": "compressor", "provider_type": "chat_completion"},
        ],
        "provider_settings": {
            "agent_runner_type": "local",
            "default_provider_id": "chat-main",
            "fallback_chat_models": ["chat-backup"],
            "request_max_retries": 8,
            "default_personality": "developer",
            "llm_safety_mode": False,
            "max_agent_step": 48,
            "tool_call_timeout": 96,
            "sanitize_context_by_modalities": True,
            "context_limit_reached_strategy": "llm_compress",
            "llm_compress_instruction": "Keep decisions",
            "llm_compress_provider_id": "compressor",
            "max_context_length": 24,
            "dequeue_context_length": 4,
        },
        "agent_runner": {
            "runner_type": "local",
            "config": get_agent_runner_config_default("local"),
        },
    }

    default_config = {
        "provider": [
            {"id": "chat-main", "provider_type": "chat_completion"},
            {"id": "chat-backup", "provider_type": "chat_completion"},
            {"id": "compressor", "provider_type": "chat_completion"},
        ]
    }
    assert _migrate_agent_runner_config(config, default_config)

    assert config["agent_runner"] == {
        "runner_type": "local",
        "config": {
            "model": {
                "provider_id": "chat-main",
                "fallback_provider_ids": ["chat-backup"],
                "request_max_retries": 8,
            },
            "persona": {
                "persona_id": "developer",
                "safety_mode": False,
                "safety_mode_strategy": "system_prompt",
            },
            "compression": {
                "max_turns": 24,
                "trim_turns": 4,
                "overflow_strategy": "llm_compress",
                "instruction": "Keep decisions",
                "keep_recent_ratio": 0.15,
                "provider_id": "compressor",
                "fallback_max_tokens": 128000,
            },
            "misc": {
                "max_steps": 48,
                "tool_schema_mode": "full",
                "tool_call_timeout": 96,
                "sanitize_context_by_modalities": True,
            },
        },
    }
    assert not set(config["provider_settings"]).intersection(
        {
            "agent_runner_type",
            "default_provider_id",
            "fallback_chat_models",
            "default_personality",
            "llm_compress_provider_id",
            "tool_call_timeout",
            "sanitize_context_by_modalities",
        }
    )


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

    _migrate_agent_runner_config(config, global_config)

    runner_config = config["agent_runner"]["config"]
    assert runner_config["model"]["provider_id"] == ""
    assert runner_config["model"]["fallback_provider_ids"] == ["available"]
    assert runner_config["compression"]["provider_id"] == ""


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

    assert _migrate_agent_runner_config(config, global_config)
    assert finalize_config_migrations([global_config, config])

    runner_config = config["agent_runner"]["config"]
    assert config["agent_runner"]["runner_type"] == runner_type
    assert runner_config[expected_key] == provider_config[expected_key]
    assert runner_config["persona_id"] == "operator"
    assert runner_config["max_steps"] == 30
    assert not {
        "id",
        "type",
        "provider",
        "provider_type",
        "enable",
        "proxy",
    }.intersection(runner_config)
    assert global_config["provider"] == []


def test_profile_migration_merges_runner_provider_source(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    data_path = tmp_path / "data"
    profile_path = data_path / "config" / "abconf_profile.json"
    profile_path.parent.mkdir(parents=True)
    default_config = {
        "provider_sources": [
            {
                "id": "dify-source",
                "type": "dify",
                "provider_type": "agent_runner",
                "dify_api_key": "source-key",
                "dify_api_base": "https://example.test/v1",
            }
        ],
        "provider": [
            {
                "id": "dify-provider",
                "provider_source_id": "dify-source",
                "enable": True,
            }
        ],
    }
    (data_path / "cmd_config.json").write_text(
        json.dumps(default_config), encoding="utf-8"
    )
    profile_config = {
        "config_version": 2,
        "provider": [],
        "provider_settings": {
            "agent_runner_type": "dify",
            "dify_agent_runner_provider_id": "dify-provider",
        },
    }
    profile_path.write_text(json.dumps(profile_config), encoding="utf-8")
    monkeypatch.setattr(
        "astrbot.core.config.agent_runner_migration.get_astrbot_config_path",
        lambda: str(profile_path.parent),
    )
    monkeypatch.setattr(
        "astrbot.core.config.agent_runner_migration.get_astrbot_data_path",
        lambda: str(data_path),
    )

    loaded = AstrBotConfig(config_path=str(profile_path))

    assert loaded["agent_runner"]["runner_type"] == "dify"
    assert loaded["agent_runner"]["config"]["dify_api_key"] == "source-key"
    assert (
        loaded["agent_runner"]["config"]["dify_api_base"] == "https://example.test/v1"
    )
    assert "provider_source_id" not in loaded["agent_runner"]["config"]

    assert finalize_config_migrations([default_config, loaded])
    assert default_config["provider"] == []
    assert default_config["provider_sources"] == []


def test_finalize_removes_third_party_typed_runner_sources():
    config = {
        "provider_sources": [
            {"id": "dify-source", "type": "dify", "provider_type": "dify"},
            {
                "id": "chat-source",
                "type": "openai_chat_completions",
                "provider_type": "chat_completion",
            },
        ],
        "provider": [
            {
                "id": "dify-provider",
                "type": "dify",
                "provider_type": "agent_runner",
                "provider_source_id": "dify-source",
            },
            {
                "id": "chat-provider",
                "type": "openai_chat_completions",
                "provider_type": "chat_completion",
                "provider_source_id": "chat-source",
            },
        ],
    }

    assert finalize_config_migrations([config])
    assert [provider["id"] for provider in config["provider"]] == ["chat-provider"]
    assert [source["id"] for source in config["provider_sources"]] == ["chat-source"]


def test_finalize_deletes_agent_runner_sources_even_if_still_referenced():
    config = {
        "provider_sources": [
            {"id": "dify-source", "type": "dify", "provider_type": "agent_runner"}
        ],
        "provider": [
            {
                "id": "chat-provider",
                "type": "openai_chat_completions",
                "provider_type": "chat_completion",
                "provider_source_id": "dify-source",
            }
        ],
    }

    assert finalize_config_migrations([config])
    assert [provider["id"] for provider in config["provider"]] == ["chat-provider"]
    assert config["provider_sources"] == []


def test_finalize_preserves_chat_sources_referenced_by_remaining_providers():
    config = {
        "provider_sources": [
            {
                "id": "chat-source",
                "type": "openai_chat_completions",
                "provider_type": "chat_completion",
            }
        ],
        "provider": [
            {
                "id": "runner-provider",
                "type": "dify",
                "provider_type": "agent_runner",
                "provider_source_id": "chat-source",
            },
            {
                "id": "chat-provider",
                "type": "openai_chat_completions",
                "provider_type": "chat_completion",
                "provider_source_id": "chat-source",
            },
        ],
    }

    assert finalize_config_migrations([config])
    assert [provider["id"] for provider in config["provider"]] == ["chat-provider"]
    assert config["provider_sources"] == [
        {
            "id": "chat-source",
            "type": "openai_chat_completions",
            "provider_type": "chat_completion",
        }
    ]


def test_missing_third_party_provider_uses_runner_defaults():
    config = {
        "provider": [],
        "provider_settings": {
            "agent_runner_type": "coze",
            "coze_agent_runner_provider_id": "missing",
            "default_personality": "operator",
        },
    }

    _migrate_agent_runner_config(config)

    expected = get_agent_runner_config_default("coze")
    expected["persona_id"] = "operator"
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

    _migrate_agent_runner_config(chat_config, global_config)
    _migrate_agent_runner_config(runner_config, global_config)

    assert chat_config["agent_runner"]["runner_type"] == "local"
    assert chat_config["agent_runner"]["config"]["model"]["provider_id"] == "chat-model"
    assert runner_config["agent_runner"]["runner_type"] == "dify"
    assert runner_config["agent_runner"]["config"]["dify_api_key"] == "secret"


def test_multiple_profiles_can_copy_one_provider_and_migration_is_idempotent():
    global_config = {
        "provider_sources": [
            {
                "id": "deerflow-source",
                "type": "deerflow",
                "provider_type": "agent_runner",
            },
            {
                "id": "chat-source",
                "type": "openai_chat_completions",
                "provider_type": "chat_completion",
            },
        ],
        "provider": [
            {
                "id": "shared-deerflow",
                "type": "deerflow",
                "provider_type": "agent_runner",
                "provider_source_id": "deerflow-source",
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
            {
                "id": "chat-model",
                "type": "openai_chat_completions",
                "provider_type": "chat_completion",
                "provider_source_id": "chat-source",
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
        _migrate_agent_runner_config(profile, global_config)
        profiles.append(profile)

    finalize_config_migrations([global_config, *profiles])
    first_result = copy.deepcopy([global_config, *profiles])

    assert [
        profile["agent_runner"]["config"]["deerflow_api_key"] for profile in profiles
    ] == ["shared-key", "shared-key"]
    assert [
        profile["agent_runner"]["config"]["persona_id"] for profile in profiles
    ] == ["one", "two"]
    assert global_config["provider"] == [
        {
            "id": "chat-model",
            "type": "openai_chat_completions",
            "provider_type": "chat_completion",
            "provider_source_id": "chat-source",
        }
    ]
    assert global_config["provider_sources"] == [
        {
            "id": "chat-source",
            "type": "openai_chat_completions",
            "provider_type": "chat_completion",
        }
    ]
    assert not finalize_config_migrations([global_config, *profiles])
    assert [global_config, *profiles] == first_result


def test_new_agent_runner_config_is_authoritative_and_opaque_on_reload(tmp_path):
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["config_version"] = 2
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


def test_unhashable_fallback_entries_do_not_crash_migration():
    config = {
        "provider": [],
        "provider_settings": {
            "agent_runner_type": "local",
            "default_provider_id": {"id": "nested"},
            "fallback_chat_models": [
                {"id": "dict-fallback"},
                ["list"],
                "available",
                "",
            ],
            "llm_compress_provider_id": ["not-a-string"],
        },
    }
    global_config = {
        "provider": [{"id": "available", "provider_type": "chat_completion"}]
    }

    _migrate_agent_runner_config(config, global_config)

    runner_config = config["agent_runner"]["config"]
    assert runner_config["model"]["provider_id"] == ""
    assert runner_config["model"]["fallback_provider_ids"] == ["available"]
    assert runner_config["compression"]["provider_id"] == ""


def test_third_party_proxy_and_max_steps_are_copied_from_legacy_provider():
    config = {
        "config_version": 2,
        "provider": [],
        "provider_settings": {
            "agent_runner_type": "dify",
            "dify_agent_runner_provider_id": "dify-provider",
            "max_agent_step": 12,
            "default_personality": "operator",
        },
    }
    global_config = {
        "provider": [
            {
                "id": "dify-provider",
                "type": "dify",
                "provider_type": "agent_runner",
                "dify_api_key": "dify-key",
                "proxy_mode": "custom",
                "proxy_url": "http://127.0.0.1:7890",
            }
        ]
    }

    assert _migrate_agent_runner_config(config, global_config)
    runner_config = config["agent_runner"]["config"]
    assert runner_config["proxy_mode"] == "custom"
    assert runner_config["proxy_url"] == "http://127.0.0.1:7890"
    assert runner_config["max_steps"] == 12
    assert runner_config["persona_id"] == "operator"
    assert "proxy" not in runner_config


def test_string_proxy_is_upgraded_to_three_state():
    custom = normalize_agent_runner(
        {
            "runner_type": "coze",
            "config": {"proxy": "http://proxy.example:8080"},
        }
    )
    inherit = normalize_agent_runner(
        {
            "runner_type": "coze",
            "config": {"proxy": ""},
        }
    )

    assert custom["config"]["proxy_mode"] == "custom"
    assert custom["config"]["proxy_url"] == "http://proxy.example:8080"
    assert "proxy" not in custom["config"]
    assert inherit["config"]["proxy_mode"] == "inherit"
    assert inherit["config"]["proxy_url"] == ""
    assert "proxy" not in inherit["config"]

    overridden = normalize_agent_runner(
        {
            "runner_type": "coze",
            "config": {
                "proxy": "http://legacy.example:8080",
                "proxy_mode": "inherit",
                "proxy_url": "",
            },
        }
    )
    assert overridden["config"]["proxy_mode"] == "custom"
    assert overridden["config"]["proxy_url"] == "http://legacy.example:8080"


def test_normalize_drops_non_string_fallback_ids():
    normalized = normalize_agent_runner(
        {
            "runner_type": "local",
            "config": {
                "model": {
                    "fallback_provider_ids": [
                        "keep-me",
                        {"id": "nope"},
                        12,
                        "",
                        None,
                    ]
                }
            },
        }
    )

    assert normalized["config"]["model"]["fallback_provider_ids"] == ["keep-me"]


def test_unknown_runner_type_on_load_becomes_local(tmp_path):
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["config_version"] = 3
    config["agent_runner"] = {"runner_type": "unknown-runner", "config": {}}
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    loaded = AstrBotConfig(config_path=str(config_path))

    assert loaded["agent_runner"] == {
        "runner_type": "local",
        "config": get_agent_runner_config_default("local"),
    }


def test_normalize_for_load_repairs_invalid_runner_without_raising():
    repaired = normalize_agent_runner_for_load({"runner_type": "nope", "config": {}})
    assert repaired["runner_type"] == "local"
    assert repaired["config"] == get_agent_runner_config_default("local")


def test_get_persona_id_reads_local_and_third_party_fields():
    assert (
        get_persona_id(
            {
                "runner_type": "local",
                "config": {"persona": {"persona_id": "developer"}},
            }
        )
        == "developer"
    )
    assert (
        get_persona_id({"runner_type": "dify", "config": {"persona_id": "operator"}})
        == "operator"
    )
    assert get_persona_id({"runner_type": "dify", "config": {}}) == "default"
    assert get_persona_id({"runner_type": "dify", "config": {"persona_id": ""}}) == (
        "default"
    )
