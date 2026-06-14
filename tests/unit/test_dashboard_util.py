"""Tests for dashboard route utility helpers."""

from astrbot.dashboard.services.config_service import get_schema_item, validate_config


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
