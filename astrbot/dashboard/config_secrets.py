"""Write-only handling for secrets in dashboard configuration payloads."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

SECRET_UNCHANGED_SENTINEL = "__ASTRBOT_SECRET_UNCHANGED__"
HARD_PROTECTED_SECRET_PATHS = {
    ("dashboard", "jwt_secret"),
    ("dashboard", "plugin_asset_jwt_secret"),
    ("dashboard", "password"),
    ("dashboard", "pbkdf2_password"),
    ("dashboard", "password_storage_upgraded"),
    ("dashboard", "password_change_required"),
    ("dashboard", "totp", "secret"),
    ("dashboard", "totp", "recovery_code_hash"),
}
TOTP_PROTECTED_SECRET_PATHS = {
    ("dashboard", "totp", "secret"),
    ("dashboard", "totp", "recovery_code_hash"),
}
SECURITY_POLICY_PATH_PREFIXES = {
    ("security", "outbound_fetch"),
    ("dashboard", "access_mode"),
    ("dashboard", "reverse_proxy"),
}

_SENSITIVE_EXACT_KEYS = {
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "access_key",
    "private_key",
    "recovery_code_hash",
}
_SENSITIVE_KEY_SUFFIXES = (
    "_password",
    "_passwd",
    "_secret",
    "_token",
    "_api_key",
    "_access_key",
    "_private_key",
)


class ConfigSecretPermissionError(ValueError):
    """Raised when an API key tries to modify a write-only configuration value."""


def _is_sensitive_path(path: tuple[str | int, ...], metadata: object = None) -> bool:
    """Return whether a configuration location must never be read back.

    Args:
        path: Nested configuration path.
        metadata: Optional schema metadata for the current location.

    Returns:
        True when the field is a secret or protected credential.
    """
    if (
        tuple(part for part in path if isinstance(part, str))
        in HARD_PROTECTED_SECRET_PATHS
    ):
        return True
    if isinstance(metadata, Mapping) and metadata.get("secret") is True:
        return True
    if not path or not isinstance(path[-1], str):
        return False
    key = path[-1].lower()
    return key in _SENSITIVE_EXACT_KEYS or key.endswith(_SENSITIVE_KEY_SUFFIXES)


def _child_metadata(metadata: object, key: str | int) -> object:
    """Locate metadata for a direct configuration child.

    Args:
        metadata: Parent schema node.
        key: Child key or list index.

    Returns:
        Matching schema node when available.
    """
    if not isinstance(metadata, Mapping):
        return None
    if isinstance(key, str):
        for container_key in ("items", "metadata", "config_template"):
            container = metadata.get(container_key)
            if isinstance(container, Mapping) and key in container:
                return container[key]
        if key in metadata:
            return metadata[key]
    return metadata.get("items")


def redact_config_for_response(
    config: dict[str, Any], metadata: dict | None = None
) -> dict:
    """Create a response-safe configuration copy without credential values.

    Args:
        config: Configuration object to serialize.
        metadata: Optional configuration schema metadata.

    Returns:
        Deep copied configuration with configured secrets replaced by a sentinel.
    """

    def redact(value: Any, path: tuple[str | int, ...], schema: object) -> Any:
        if _is_sensitive_path(path, schema):
            return value if value in (None, "", [], {}) else SECRET_UNCHANGED_SENTINEL
        if isinstance(value, dict):
            return {
                key: redact(child, (*path, key), _child_metadata(schema, key))
                for key, child in value.items()
            }
        if isinstance(value, list):
            return [
                redact(child, (*path, index), _child_metadata(schema, index))
                for index, child in enumerate(value)
            ]
        return copy.deepcopy(value)

    return redact(config, (), metadata)


def merge_secret_fields(
    incoming: dict[str, Any],
    current: dict[str, Any],
    metadata: dict | None = None,
    *,
    allow_secret_change: bool,
    allow_security_policy_change: bool = False,
    allow_totp_secret_change: bool = False,
) -> dict[str, Any]:
    """Merge incoming config while preserving sentinels and enforcing write scope.

    Args:
        incoming: Full configuration payload submitted by a client.
        current: Current persisted configuration.
        metadata: Optional configuration schema metadata.
        allow_secret_change: Whether the caller may replace or clear secrets.
        allow_security_policy_change: Whether the caller may change network and
            Dashboard exposure policy.
        allow_totp_secret_change: Whether a Dashboard session may submit a TOTP
            secret change for the service layer's separate current-code check.

    Returns:
        A deep copied, merged configuration ready for existing validation.

    Raises:
        ConfigSecretPermissionError: If an unauthorized caller changes a secret.
    """

    def merge(value: Any, old: Any, path: tuple[str | int, ...], schema: object) -> Any:
        security_policy = any(
            path[: len(prefix)] == prefix for prefix in SECURITY_POLICY_PATH_PREFIXES
        )
        if security_policy and value != old and not allow_security_policy_change:
            raise ConfigSecretPermissionError(
                "config:security scope is required to change security policy"
            )
        sensitive = _is_sensitive_path(path, schema)
        if sensitive:
            if value == SECRET_UNCHANGED_SENTINEL:
                return copy.deepcopy(old)
            string_path = tuple(part for part in path if isinstance(part, str))
            protected_change = (
                string_path in HARD_PROTECTED_SECRET_PATHS and value != old
            )
            totp_change_allowed = (
                string_path in TOTP_PROTECTED_SECRET_PATHS and allow_totp_secret_change
            )
            if protected_change and not totp_change_allowed:
                raise ConfigSecretPermissionError(
                    "Dashboard authentication state cannot be changed through config APIs"
                )
            if value != old and not allow_secret_change:
                raise ConfigSecretPermissionError(
                    "config:secrets scope is required to change secrets"
                )
            return copy.deepcopy(value)
        if isinstance(value, dict):
            old_dict = old if isinstance(old, dict) else {}
            return {
                key: merge(
                    child, old_dict.get(key), (*path, key), _child_metadata(schema, key)
                )
                for key, child in value.items()
            }
        if isinstance(value, list):
            old_list = old if isinstance(old, list) else []
            return [
                merge(
                    child,
                    old_list[index] if index < len(old_list) else None,
                    (*path, index),
                    _child_metadata(schema, index),
                )
                for index, child in enumerate(value)
            ]
        return copy.deepcopy(value)

    return merge(incoming, current, (), metadata)
