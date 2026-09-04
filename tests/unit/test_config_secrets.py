"""Regression tests for write-only dashboard configuration values."""

import pytest

from astrbot.dashboard.config_secrets import (
    SECRET_UNCHANGED_SENTINEL,
    ConfigSecretPermissionError,
    merge_secret_fields,
    redact_config_for_response,
)


def test_redact_config_keeps_empty_secret_and_hides_configured_secret():
    """Configured credentials must never be serialized into a response."""
    source = {"provider": {"api_key": "provider-secret", "empty_token": ""}}

    redacted = redact_config_for_response(source)

    assert redacted["provider"]["api_key"] == SECRET_UNCHANGED_SENTINEL
    assert redacted["provider"]["empty_token"] == ""
    assert source["provider"]["api_key"] == "provider-secret"


def test_redact_config_always_hides_dashboard_signing_secret():
    """Hard-protected signing keys remain write-only without schema metadata."""
    redacted = redact_config_for_response({"dashboard": {"jwt_secret": "secret"}})

    assert redacted["dashboard"]["jwt_secret"] == SECRET_UNCHANGED_SENTINEL


def test_non_secret_token_count_is_not_redacted():
    """Token-budget fields must not be mistaken for authentication tokens."""
    source = {"fallback_max_context_tokens": 128000, "request_max_tokens": 4096}
    assert redact_config_for_response(source) == source


def test_merge_sentinel_preserves_existing_secret():
    """A form save without touching a secret must preserve the stored value."""
    merged = merge_secret_fields(
        {"provider": {"api_key": SECRET_UNCHANGED_SENTINEL}},
        {"provider": {"api_key": "stored-secret"}},
        allow_secret_change=False,
    )

    assert merged["provider"]["api_key"] == "stored-secret"


def test_merge_rejects_api_key_secret_change_without_scope():
    """The base config scope cannot replace write-only credentials."""
    with pytest.raises(ConfigSecretPermissionError):
        merge_secret_fields(
            {"provider": {"api_key": "replacement"}},
            {"provider": {"api_key": "stored-secret"}},
            allow_secret_change=False,
        )


def test_merge_allows_authorized_secret_change():
    """The dedicated secrets scope can replace an existing credential."""
    merged = merge_secret_fields(
        {"provider": {"api_key": "replacement"}},
        {"provider": {"api_key": "stored-secret"}},
        allow_secret_change=True,
    )

    assert merged["provider"]["api_key"] == "replacement"


def test_hard_protected_signing_secret_cannot_be_changed_with_scope():
    """Even config:secrets cannot replace internal Dashboard signing keys."""
    with pytest.raises(ConfigSecretPermissionError, match="authentication state"):
        merge_secret_fields(
            {"dashboard": {"jwt_secret": "replacement"}},
            {"dashboard": {"jwt_secret": "stored-secret"}},
            allow_secret_change=True,
        )


def test_totp_secret_change_requires_interactive_dashboard_context():
    """A scoped API key cannot rewrite TOTP state as ordinary config data."""
    current = {"dashboard": {"totp": {"secret": "stored-secret"}}}
    incoming = {"dashboard": {"totp": {"secret": "replacement"}}}

    with pytest.raises(ConfigSecretPermissionError, match="authentication state"):
        merge_secret_fields(
            incoming,
            current,
            allow_secret_change=True,
            allow_totp_secret_change=False,
        )

    assert merge_secret_fields(
        incoming,
        current,
        allow_secret_change=True,
        allow_totp_secret_change=True,
    ) == incoming


def test_merge_rejects_security_policy_change_without_scope():
    """The base config scope cannot relax private-network policy."""
    with pytest.raises(ConfigSecretPermissionError, match="config:security"):
        merge_secret_fields(
            {
                "security": {
                    "outbound_fetch": {
                        "media_private_targets": [
                            {"host": "internal", "cidrs": ["10.0.0.0/8"]}
                        ]
                    }
                }
            },
            {"security": {"outbound_fetch": {"media_private_targets": []}}},
            allow_secret_change=False,
            allow_security_policy_change=False,
        )


def test_merge_allows_security_policy_change_with_scope():
    """The dedicated security scope can add an exact private target rule."""
    incoming = {
        "security": {
            "outbound_fetch": {
                "media_private_targets": [
                    {"host": "internal", "cidrs": ["10.0.0.0/8"]}
                ]
            }
        }
    }
    merged = merge_secret_fields(
        incoming,
        {"security": {"outbound_fetch": {"media_private_targets": []}}},
        allow_secret_change=False,
        allow_security_policy_change=True,
    )
    assert merged == incoming
