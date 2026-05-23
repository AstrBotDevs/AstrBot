from __future__ import annotations

from typing import Any


def tool_available_in_runtime(tool: Any, runtime: str) -> bool:
    """Return whether a tool should be exposed for the computer-use runtime.

    Provider-specific sandbox tools are registered once when their provider is
    enabled. They are visible to all sandbox sessions and hidden from local/none
    runtimes.
    """
    tool_provider = getattr(tool, "sandbox_provider_id", None)
    if not tool_provider:
        return True
    return runtime == "sandbox"


def mark_tool_as_sandbox_provider_tool(tool: Any, provider_id: str) -> Any:
    provider_id = _normalize_provider_id(provider_id)
    tool.sandbox_provider_id = provider_id
    marker = f"[Sandbox provider-specific tool: {provider_id}]"
    description = str(getattr(tool, "description", "") or "")
    if marker not in description:
        tool.description = (
            f"{marker} This tool only works when the current sandbox uses provider "
            f"'{provider_id}'. If the current sandbox uses another provider, switch or "
            f"create a '{provider_id}' sandbox first. {description}"
        ).strip()
    return tool


def _normalize_provider_id(provider_id: str | None) -> str:
    return "" if provider_id is None else str(provider_id).strip().lower()
