"""Tests for dashboard route utility helpers."""

from unittest.mock import Mock

import pytest

from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.dashboard.services.config_service import (
    get_schema_item,
    save_config,
    validate_config,
)


@pytest.mark.parametrize("key", ["", "sk-decision", "$DECISION_API_KEY"])
def test_save_http_proxy_with_decision_and_chat_keys(key):
    payload = {
        "http_proxy": "http://127.0.0.1:7890",
        "agent_runner": {"runner_type": "local"},
        "provider": [
            {"type": "system_one_decision", "key": key},
            {"type": "openai_chat_completion", "key": ["sk-chat"]},
        ],
    }
    config = Mock(keys=lambda: [])

    save_config(payload, config, is_core=True)

    saved = config.save_config.call_args.args[0]
    assert saved["http_proxy"] == "http://127.0.0.1:7890"
    assert saved["provider"][0]["key"] == key
    assert saved["provider"][1]["key"] == ["sk-chat"]
    assert CONFIG_METADATA_2["provider_group"]["metadata"]["provider"]["items"][
        "key"
    ]["type"] == "list"


@pytest.mark.parametrize(
    ("provider_type", "key"),
    [
        ("system_one_decision", ["sk-decision"]),
        ("openai_chat_completion", "sk-chat"),
    ],
)
def test_core_config_rejects_wrong_provider_key_shape(provider_type, key):
    errors, _ = validate_config(
        {"provider": [{"type": provider_type, "key": key}]},
        CONFIG_METADATA_2,
        is_core=True,
    )

    assert errors
    assert all("provider.key" in error for error in errors)


def test_plugin_provider_key_validation_uses_its_own_schema():
    schema = {
        "provider": {
            "type": "list",
            "items": {"key": {"type": "list"}},
        },
    }
    errors, _ = validate_config(
        {"provider": [{"type": "system_one_decision", "key": "sk-plugin"}]},
        schema,
        is_core=False,
    )

    assert errors


def test_get_schema_item_template_list_file_item():
    schema = {
        "demo_templates": {
            "type": "template_list",
            "templates": {
                "api_provider": {
                    "items": {
                        "tls_certificate_files": {"type": "file"},
                    },
                },
            },
        },
    }

    meta = get_schema_item(
        schema,
        "demo_templates.templates.api_provider.tls_certificate_files",
    )

    assert meta == {"type": "file"}


def test_get_schema_item_nested_template_list_file_item():
    schema = {
        "group": {
            "type": "object",
            "items": {
                "demo_templates": {
                    "type": "template_list",
                    "templates": {
                        "nested_profile": {
                            "items": {
                                "profile": {
                                    "type": "object",
                                    "items": {
                                        "attachments": {"type": "file"},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    }

    meta = get_schema_item(
        schema,
        "group.demo_templates.templates.nested_profile.profile.attachments",
    )

    assert meta == {"type": "file"}


def test_validate_config_template_list_file_path_uses_template_schema_path():
    schema = {
        "demo_templates": {
            "type": "template_list",
            "templates": {
                "api_provider": {
                    "items": {
                        "tls_certificate_files": {"type": "file"},
                    },
                },
            },
        },
    }
    data = {
        "demo_templates": [
            {
                "__template_key": "api_provider",
                "tls_certificate_files": [
                    "files/demo_templates/templates/api_provider/tls_certificate_files/cert.pem"
                ],
            }
        ]
    }

    errors, validated = validate_config(data, schema, is_core=False)

    assert errors == []
    assert validated == data
