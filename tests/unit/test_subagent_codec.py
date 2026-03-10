from __future__ import annotations

import pytest

from astrbot.core.subagent.codec import decode_subagent_config, encode_subagent_config
from astrbot.core.subagent.models import ToolsScope


def test_decode_subagent_config_accepts_legacy_fields_and_infers_scope():
    config, diagnostics = decode_subagent_config(
        {
            "enable": True,
            "agents": [
                {
                    "name": "writer",
                    "enable": True,
                    "persona_id": "p1",
                    "system_prompt": "legacy prompt",
                    "x-note": "abc",
                }
            ],
            "x-ext": {"k": "v"},
        }
    )
    assert config.main_enable is True
    assert config.agents[0].tools_scope == ToolsScope.PERSONA
    assert config.agents[0].instructions == "legacy prompt"
    assert config.extensions["x-ext"] == {"k": "v"}
    assert any("legacy field `enable`" in d for d in diagnostics)


def test_decode_subagent_config_rejects_unknown_non_extension_fields():
    with pytest.raises(ValueError):
        decode_subagent_config(
            {
                "main_enable": True,
                "unknown_field": 1,
            }
        )


def test_encode_subagent_config_to_transitional_dual_fields():
    config, _ = decode_subagent_config(
        {
            "main_enable": True,
            "agents": [
                {
                    "name": "planner",
                    "enabled": True,
                    "tools_scope": "list",
                    "tools": ["tool_a"],
                    "instructions": "hello",
                }
            ],
        }
    )
    payload = encode_subagent_config(config)
    assert payload["main_enable"] is True
    assert payload["agents"][0]["name"] == "planner"
    assert payload["agents"][0]["tools"] == ["tool_a"]
    assert payload["agents"][0]["instructions"] == "hello"
    assert payload["agents"][0]["system_prompt"] == "hello"


def test_decode_subagent_config_agent_extension_passthrough():
    config, _ = decode_subagent_config(
        {
            "main_enable": True,
            "agents": [
                {
                    "name": "writer",
                    "enabled": True,
                    "tools_scope": "none",
                    "x-tag": "tag-1",
                }
            ],
        }
    )
    assert config.agents[0].extensions["x-tag"] == "tag-1"


def test_decode_subagent_config_explicit_tools_scope_overrides_tools_inference():
    config, _ = decode_subagent_config(
        {
            "main_enable": True,
            "agents": [
                {
                    "name": "writer",
                    "enabled": True,
                    "tools_scope": "none",
                    "tools": ["tool_a", "tool_b"],
                }
            ],
        }
    )
    assert config.agents[0].tools_scope == ToolsScope.NONE
    assert config.agents[0].tools is None


def test_encode_decode_roundtrip_with_instructions_has_no_legacy_warning():
    config, _ = decode_subagent_config(
        {
            "main_enable": True,
            "agents": [
                {
                    "name": "writer",
                    "enabled": True,
                    "instructions": "do work",
                }
            ],
        }
    )
    encoded = encode_subagent_config(config)
    _, diagnostics = decode_subagent_config(encoded)
    assert not any("legacy field `agents[0].system_prompt`" in d for d in diagnostics)


def test_decode_subagent_config_parses_boolean_strings():
    config, _ = decode_subagent_config(
        {
            "main_enable": "false",
            "remove_main_duplicate_tools": "1",
            "agents": [
                {
                    "name": "writer",
                    "enabled": "0",
                    "instructions": "do work",
                }
            ],
        }
    )
    assert config.main_enable is False
    assert config.remove_main_duplicate_tools is True
    assert config.agents[0].enabled is False


def test_decode_subagent_config_rejects_invalid_boolean_value():
    with pytest.raises(ValueError):
        decode_subagent_config(
            {
                "main_enable": "not-a-bool",
                "agents": [{"name": "writer"}],
            }
        )


def test_decode_subagent_config_wraps_invalid_tools_scope_with_agent_index():
    with pytest.raises(ValueError, match=r"invalid subagent at agents\[0\]"):
        decode_subagent_config(
            {
                "main_enable": True,
                "agents": [
                    {
                        "name": "writer",
                        "tools_scope": "invalid-scope",
                    }
                ],
            }
        )
