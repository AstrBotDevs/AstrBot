from __future__ import annotations

from collections.abc import Callable
from typing import Any


def resolve_sandbox_provider_bindings(
    provider_id: str | None,
    tool_mgr: Any,
    provider_info_lookup: Callable[[str], dict | None],
) -> tuple[dict | None, list[Any]]:
    """Return provider metadata and active provider tools for sandbox mode."""
    normalized_provider_id = _normalize_provider_id(provider_id)
    provider_info = provider_info_lookup(normalized_provider_id)
    if not provider_info:
        return None, []

    tools = []
    for tool_name in provider_info.get("tool_names", []):
        tool = tool_mgr.get_func(tool_name)
        if tool and getattr(tool, "active", True):
            tools.append(tool)
    return provider_info, tools


def resolve_effective_sandbox_provider_id(
    session_id: str,
    fallback_provider_id: str | None,
    current_provider_lookup: Callable[[str], str | None],
) -> str | None:
    provider_id = _normalize_provider_id(current_provider_lookup(session_id))
    if provider_id:
        return provider_id

    return _normalize_provider_id(fallback_provider_id)


def tool_matches_sandbox_provider(
    tool: Any, runtime: str, provider_id: str | None
) -> bool:
    tool_provider = getattr(tool, "sandbox_provider_id", None)
    if not tool_provider:
        return True
    if runtime != "sandbox":
        return False
    normalized_provider_id = _normalize_provider_id(provider_id)
    return str(tool_provider).lower() == normalized_provider_id


def _normalize_provider_id(provider_id: str | None) -> str:
    return "" if provider_id is None else str(provider_id).strip().lower()
