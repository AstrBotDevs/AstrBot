import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from astrbot.dashboard.routes.config import (
    restore_masked_provider_config,
    sanitize_provider_config,
)


def test_sanitize_provider_config_masks_sensitive_fields():
    raw = {
        "id": "openai",
        "type": "openai_chat_completion",
        "key": ["sk-123"],
        "custom_headers": {
            "Authorization": "Bearer sk-abc",
            "X-Trace": "ok",
        },
        "nested": {
            "api_key": "secret-key",
            "token": "tkn",
            "keep": "value",
        },
    }

    sanitized = sanitize_provider_config(raw)

    assert sanitized["key"] == ["***"]
    assert sanitized["custom_headers"]["Authorization"] == "***"
    assert sanitized["custom_headers"]["X-Trace"] == "ok"
    assert sanitized["nested"]["api_key"] == "***"
    assert sanitized["nested"]["token"] == "***"
    assert sanitized["nested"]["keep"] == "value"


def test_sanitize_provider_config_keeps_non_sensitive_fields():
    raw = {
        "id": "provider-id",
        "model": "gpt-4.1",
        "provider_type": "chat_completion",
    }

    sanitized = sanitize_provider_config(raw)

    assert sanitized == raw


def test_sanitize_provider_config_does_not_mask_non_secret_token_fields():
    raw = {
        "max_tokens": 4096,
        "token_limit": 8192,
        "monkey": "banana",
    }

    sanitized = sanitize_provider_config(raw)

    assert sanitized["max_tokens"] == 4096
    assert sanitized["token_limit"] == 8192
    assert sanitized["monkey"] == "banana"


def test_restore_masked_provider_config_recovers_existing_secrets():
    old = {
        "id": "openai",
        "key": ["sk-old"],
        "custom_headers": {
            "Authorization": "Bearer old",
            "X-Trace": "old-trace",
        },
        "max_tokens": 1024,
        "enable": True,
    }
    sanitized = sanitize_provider_config(old)
    sanitized["enable"] = False
    sanitized["max_tokens"] = 2048

    restored = restore_masked_provider_config(sanitized, old)

    assert restored["key"] == ["sk-old"]
    assert restored["custom_headers"]["Authorization"] == "Bearer old"
    assert restored["custom_headers"]["X-Trace"] == "old-trace"
    assert restored["enable"] is False
    assert restored["max_tokens"] == 2048
