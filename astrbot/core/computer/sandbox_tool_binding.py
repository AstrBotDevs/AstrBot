from __future__ import annotations

from typing import Any


def resolve_sandbox_provider_bindings(
    provider_id: str | None,
    tool_mgr: Any,
) -> tuple[dict | None, list[Any]]:
    """Return provider metadata and active provider tools for sandbox mode."""
    from astrbot.core.computer.computer_client import get_sandbox_provider_info

    normalized_provider_id = "" if provider_id is None else str(provider_id).lower()
    provider_info = get_sandbox_provider_info(normalized_provider_id)
    if not provider_info:
        return None, []

    tools = []
    for tool_name in provider_info.get("tool_names", []):
        tool = tool_mgr.get_func(tool_name)
        if tool and getattr(tool, "active", True):
            tools.append(tool)
    return provider_info, tools


def tool_matches_sandbox_provider(tool: Any, runtime: str, provider_id: str | None) -> bool:
    tool_provider = getattr(tool, "sandbox_provider_id", None)
    if not tool_provider:
        return True
    if runtime != "sandbox":
        return False
    normalized_provider_id = "" if provider_id is None else str(provider_id).lower()
    return str(tool_provider).lower() == normalized_provider_id
