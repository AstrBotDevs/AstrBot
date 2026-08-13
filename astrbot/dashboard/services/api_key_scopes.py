"""Dashboard API-key scope registry and authorization helpers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

# Keep this fixed when adding Dashboard-only scopes. Existing rows
# with ``scopes = NULL`` predate explicit scope storage and must not silently
# acquire capabilities introduced in the future.
DEFAULT_API_KEY_SCOPES = (
    "bot",
    "provider",
    "persona",
    "im",
    "config",
    "chat",
    "kb",
    "memory",
    "data",
    "file",
    "plugin",
    "mcp",
    "skill",
)
DASHBOARD_API_KEY_SCOPES = (*DEFAULT_API_KEY_SCOPES,)

SCOPE_INCLUDES: dict[str, tuple[str, ...]] = {
    "config": ("bot", "provider"),
}


class ApiKeyScopeError(ValueError):
    """Raised when an API-key scope declaration is invalid."""


def _ordered_unique(scopes: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(scopes))


def effective_api_key_scopes(raw_scopes: Any) -> list[str]:
    """Return the scopes a persisted API key effectively has.

    ``NULL`` is the historical representation of the then-current baseline,
    not a wildcard.  An explicit historical ``*`` keeps its documented
    wildcard semantics and is intentionally distinct from ``NULL``.
    Invalid persisted values never grant access.
    """
    if raw_scopes is None:
        return list(DEFAULT_API_KEY_SCOPES)
    if not isinstance(raw_scopes, list):
        return []
    return _ordered_unique(
        scope
        for scope in raw_scopes
        if isinstance(scope, str)
        and (scope == "*" or scope in DASHBOARD_API_KEY_SCOPES)
    )


def normalize_api_key_scopes(raw_scopes: Any) -> list[str]:
    """Validate scopes supplied while creating an API key.

    New keys cannot request the historical wildcard.
    """
    if raw_scopes is None:
        return list(DEFAULT_API_KEY_SCOPES)
    if not isinstance(raw_scopes, list):
        raise ApiKeyScopeError("Invalid scopes")

    scopes: list[str] = []
    invalid_scopes: list[str] = []
    for scope in raw_scopes:
        if isinstance(scope, str) and scope in DASHBOARD_API_KEY_SCOPES:
            scopes.append(scope)
        else:
            invalid_scopes.append(str(scope))
    if invalid_scopes:
        raise ApiKeyScopeError(f"Invalid scopes: {', '.join(invalid_scopes)}")

    for scope in tuple(scopes):
        scopes.extend(SCOPE_INCLUDES.get(scope, ()))
    normalized = _ordered_unique(scopes)
    if not normalized:
        raise ApiKeyScopeError("At least one valid scope is required")
    return normalized


def api_key_has_scope(scopes: Iterable[str], required_scope: str) -> bool:
    """Return whether effective API-key scopes grant ``required_scope``."""
    selected = set(scopes)
    if "*" in selected:
        return True
    return required_scope in selected or any(
        required_scope in SCOPE_INCLUDES.get(scope, ()) for scope in selected
    )
