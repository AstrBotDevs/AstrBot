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


def sandbox_provider_tool(provider_id: str, **metadata: Any):
    """Mark a provider-specific sandbox tool class or instance.

    Args:
        provider_id: Sandbox provider identifier that owns the tool.
        **metadata: Optional metadata kept on the decorated object for provider
            plugins that inspect it later.

    Returns:
        A decorator that marks the tool as provider-specific.
    """

    def _decorator(tool: Any) -> Any:
        marked_tool = mark_tool_as_sandbox_provider_tool(tool, provider_id)
        for key, value in metadata.items():
            setattr(marked_tool, key, value)
        return marked_tool

    return _decorator


def _normalize_provider_id(provider_id: str | None) -> str:
    return "" if provider_id is None else str(provider_id).strip().lower()
