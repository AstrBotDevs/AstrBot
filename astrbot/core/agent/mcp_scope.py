from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

MCP_SCOPE_FIELDS = ("scopes", "agent_scope")
MCP_SCOPE_WILDCARDS = {"*", "all"}


def _normalize_scope_token(value: Any) -> str | None:
    token = str(value).strip().lower()
    return token or None


def normalize_mcp_scope_value(raw_scope: Any) -> tuple[str, ...] | None:
    """Normalize a raw MCP scope value.

    Returns:
        - None: no scope restriction (visible to all agents).
        - tuple[str, ...]: explicit allow list; empty tuple means visible to none.
    """
    if raw_scope is None:
        return None

    if isinstance(raw_scope, str):
        values: Iterable[Any] = [raw_scope]
    elif isinstance(raw_scope, Mapping):
        return ()
    elif isinstance(raw_scope, Iterable):
        values = raw_scope
    else:
        return ()

    normalized: list[str] = []
    for value in values:
        token = _normalize_scope_token(value)
        if not token:
            continue
        if token in MCP_SCOPE_WILDCARDS:
            return ("*",)
        if token not in normalized:
            normalized.append(token)
    return tuple(normalized)


def get_mcp_scopes_from_config(
    config: Mapping[str, Any] | None,
) -> tuple[str, ...] | None:
    """Extract and normalize MCP scope config from server config."""
    if not isinstance(config, Mapping):
        return None

    raw_scope = config.get("scopes", None)
    if raw_scope is None:
        raw_scope = config.get("agent_scope", None)

    return normalize_mcp_scope_value(raw_scope)


def strip_mcp_scope_fields(config: dict[str, Any]) -> None:
    """Remove MCP scope-only fields before passing config to MCP transport layer."""
    for key in MCP_SCOPE_FIELDS:
        config.pop(key, None)


def is_scope_allowed_for_agent(
    scopes: tuple[str, ...] | None,
    agent_name: str | None,
) -> bool:
    """Return whether an agent can see a tool with the given scopes."""
    if scopes is None:
        return True

    if "*" in scopes:
        return True

    normalized_agent = _normalize_scope_token(agent_name)
    if not normalized_agent:
        return False
    return normalized_agent in scopes


def is_mcp_tool_visible_to_agent(tool: Any, agent_name: str | None) -> bool:
    """Return whether an MCP tool is visible to the target agent."""
    return is_scope_allowed_for_agent(
        normalize_mcp_scope_value(getattr(tool, "mcp_server_scopes", None)),
        agent_name,
    )
