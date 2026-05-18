from __future__ import annotations

import copy
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


def resolve_all_sandbox_provider_bindings(
    tool_mgr: Any,
    providers_lookup: Callable[[], list[dict]],
) -> list[Any]:
    """Return all active provider-specific tools annotated with provider scope."""
    tools: list[Any] = []
    seen_names: set[str] = set()
    for provider_info in providers_lookup():
        provider_id = _normalize_provider_id(provider_info.get("provider_id"))
        if not provider_id:
            continue
        for tool_name in provider_info.get("tool_names", []):
            tool = tool_mgr.get_func(tool_name)
            if not tool or not getattr(tool, "active", True) or tool.name in seen_names:
                continue
            tools.append(_with_sandbox_provider_description(tool, provider_id))
            seen_names.add(tool.name)
    return tools


def resolve_effective_sandbox_provider_id(
    session_id: str,
    fallback_provider_id: str | None,
    current_provider_lookup: Callable[[str], str | None],
) -> str | None:
    provider_id = _normalize_provider_id(current_provider_lookup(session_id))
    if provider_id:
        return provider_id

    return _normalize_provider_id(fallback_provider_id)


def tool_available_in_runtime(tool: Any, runtime: str) -> bool:
    """Return whether a tool should be exposed for the computer-use runtime.

    Provider-specific sandbox tools are intentionally exposed to all sandbox
    sessions. They may bootstrap or switch their own provider-specific sandbox,
    so filtering them by the current sandbox provider would make dynamic
    provider tools unavailable until a new chat session is built.
    """
    tool_provider = getattr(tool, "sandbox_provider_id", None)
    if not tool_provider:
        return True
    return runtime == "sandbox"


def _with_sandbox_provider_description(tool: Any, provider_id: str) -> Any:
    scoped_tool = copy.copy(tool)
    scoped_tool.sandbox_provider_id = provider_id
    marker = f"[Sandbox provider-specific tool: {provider_id}]"
    description = str(getattr(scoped_tool, "description", "") or "")
    if marker not in description:
        scoped_tool.description = (
            f"{marker} This tool only works when the current sandbox uses provider "
            f"'{provider_id}'. If the current sandbox uses another provider, switch or "
            f"create a '{provider_id}' sandbox first. {description}"
        ).strip()
    return scoped_tool


def _normalize_provider_id(provider_id: str | None) -> str:
    return "" if provider_id is None else str(provider_id).strip().lower()
