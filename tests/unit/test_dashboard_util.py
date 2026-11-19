"""Tests for dashboard route utility helpers."""

import pytest

from astrbot.core.platform.platform import Platform
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


@pytest.mark.parametrize(
    "proxy_type,address,expected_valid",
    [
        ("http", "127.0.0.1:7890", True),
        ("http", "http://user:pass@127.0.0.1:7890", True),
        ("socks5", "socks5://[::1]:1080", True),
        ("http", "127.0.0.1", False),
        ("http", "http://[::1:7890", False),
        ("http", "ftp://127.0.0.1:7890", False),
        ("socks5", "http://127.0.0.1:7890", False),
    ],
)
def test_validate_config_adapter_proxy_address(proxy_type, address, expected_valid):
    schema = {
        "platform_group": {
            "metadata": {
                "platform": {
                    "type": "list",
                    "items": {
                        "type": {"type": "string"},
                        "proxy": {
                            "type": "object",
                            "items": {
                                "mode": {"type": "string"},
                                "type": {"type": "string"},
                                "address": {"type": "string"},
                            },
                        },
                    },
                }
            }
        },
        "provider_group": {"metadata": {}},
        "misc_config_group": {"metadata": {}},
    }
    data = {
        "platform": [
            {
                "type": "telegram",
                "proxy": {
                    "mode": "custom",
                    "type": proxy_type,
                    "address": address,
                },
            }
        ]
    }

    errors, _ = validate_config(data, schema, is_core=True)

    assert (not errors) is expected_valid


def test_adapter_proxy_url_rejects_scheme_type_mismatch():
    class TestPlatform(Platform):
        def run(self):
            raise NotImplementedError

        def meta(self):
            raise NotImplementedError

    adapter = TestPlatform(
        {
            "proxy": {
                "mode": "custom",
                "type": "socks5",
                "address": "http://127.0.0.1:7890",
            }
        },
        None,
    )

    with pytest.raises(ValueError, match="scheme must match"):
        _ = adapter.proxy_url
