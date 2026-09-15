from __future__ import annotations

from collections.abc import Callable
from typing import Any

from astrbot.core.agent.tool import FunctionTool
from astrbot.core.tools.registry import (
    BuiltinToolConfigRule,
    build_builtin_tool_config_rule,
)

TFunctionTool = type[FunctionTool]

_sandbox_provider_tool_config_rules: dict[str, BuiltinToolConfigRule] = {}


def tool_available_in_runtime(
    tool: Any, runtime: str, provider_id: str | None = None
) -> bool:
    """Return whether a tool should be exposed for the computer-use runtime.

    Provider-specific sandbox tools are registered once when their provider is
    enabled. They are visible to all sandbox sessions and hidden from local/none
    runtimes.
    """
    tool_provider = getattr(tool, "sandbox_provider_id", None)
    if not tool_provider:
        return True
    return runtime == "sandbox" and _normalize_provider_id(
        tool_provider
    ) == _normalize_provider_id(provider_id)


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


def sandbox_provider_tool(
    provider_id: str,
    *,
    config: dict[str, Any] | None = None,
    **metadata: Any,
) -> Callable[[TFunctionTool], TFunctionTool]:
    """Mark a FunctionTool class as belonging to a sandbox provider.

    Sandbox provider tools are plugin-owned tools with sandbox runtime semantics.
    They are not AstrBot Core builtin tools, but may still expose config tags in
    the dashboard through the same condition format as builtin tools.
    """

    normalized_provider_id = _normalize_provider_id(provider_id)

    def _register(cls: TFunctionTool) -> TFunctionTool:
        tool_name = _resolve_tool_name(cls)
        cls.sandbox_provider_id = normalized_provider_id
        for key, value in metadata.items():
            setattr(cls, key, value)
        if config is not None:
            _sandbox_provider_tool_config_rules[tool_name] = (
                build_builtin_tool_config_rule(config)
            )
        return cls

    return _register


def get_sandbox_provider_tool_config_statuses(
    tool_name: str,
    config_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rule = _sandbox_provider_tool_config_rules.get(tool_name)
    if rule is None:
        return []

    statuses: list[dict[str, Any]] = []
    for entry in config_entries:
        config = entry.get("config")
        if not isinstance(config, dict):
            continue

        conditions = rule.evaluate(config)
        enabled = bool(conditions) and all(
            bool(condition.get("matched")) for condition in conditions
        )
        statuses.append(
            {
                "conf_id": entry.get("conf_id"),
                "conf_name": entry.get("conf_name"),
                "enabled": enabled,
                "matched_conditions": [
                    condition for condition in conditions if condition.get("matched")
                ],
                "failed_conditions": [
                    condition
                    for condition in conditions
                    if not condition.get("matched")
                ],
            }
        )
    return statuses


def _resolve_tool_name(tool_cls: type[FunctionTool]) -> str:
    tool_name = getattr(tool_cls, "name", None)
    if isinstance(tool_name, str) and tool_name:
        return tool_name

    dataclass_fields = getattr(tool_cls, "__dataclass_fields__", {})
    name_field = dataclass_fields.get("name")
    if name_field is not None and isinstance(name_field.default, str):
        return name_field.default

    raise ValueError(
        f"Sandbox provider tool class {tool_cls.__module__}.{tool_cls.__name__} does not define a valid name.",
    )


def _normalize_provider_id(provider_id: str | None) -> str:
    return "" if provider_id is None else str(provider_id).strip().lower()
