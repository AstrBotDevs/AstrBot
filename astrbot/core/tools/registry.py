from __future__ import annotations

from importlib import import_module
from typing import TypeVar

from astrbot.core.agent.tool import FunctionTool

TFunctionTool = TypeVar("TFunctionTool", bound=type[FunctionTool])

_BUILTIN_TOOL_MODULES = (
    "astrbot.core.tools.cron_tools",
    "astrbot.core.tools.knowledge_base_tools",
    "astrbot.core.tools.message_tools",
    "astrbot.core.tools.web_search_tools",
)

_builtin_tool_classes_by_name: dict[str, type[FunctionTool]] = {}
_builtin_tool_names_by_class: dict[type[FunctionTool], str] = {}
_builtin_tools_loaded = False


def _resolve_builtin_tool_name(tool_cls: type[FunctionTool]) -> str:
    tool_name = getattr(tool_cls, "name", None)
    if isinstance(tool_name, str) and tool_name:
        return tool_name

    dataclass_fields = getattr(tool_cls, "__dataclass_fields__", {})
    name_field = dataclass_fields.get("name")
    if name_field is not None and isinstance(name_field.default, str):
        return name_field.default

    raise ValueError(
        f"Builtin tool class {tool_cls.__module__}.{tool_cls.__name__} does not define a valid name.",
    )


def builtin_tool(tool_cls: TFunctionTool) -> TFunctionTool:
    tool_name = _resolve_builtin_tool_name(tool_cls)
    existing = _builtin_tool_classes_by_name.get(tool_name)
    if existing is not None and existing is not tool_cls:
        raise ValueError(
            f"Builtin tool name conflict detected: {tool_name} is already registered by "
            f"{existing.__module__}.{existing.__name__}.",
        )

    _builtin_tool_classes_by_name[tool_name] = tool_cls
    _builtin_tool_names_by_class[tool_cls] = tool_name
    return tool_cls


def ensure_builtin_tools_loaded() -> None:
    global _builtin_tools_loaded
    if _builtin_tools_loaded:
        return

    for module_name in _BUILTIN_TOOL_MODULES:
        import_module(module_name)

    _builtin_tools_loaded = True


def get_builtin_tool_class(name: str) -> type[FunctionTool] | None:
    ensure_builtin_tools_loaded()
    return _builtin_tool_classes_by_name.get(name)


def get_builtin_tool_name(tool_cls: type[FunctionTool]) -> str | None:
    ensure_builtin_tools_loaded()
    return _builtin_tool_names_by_class.get(tool_cls)


def iter_builtin_tool_classes() -> tuple[type[FunctionTool], ...]:
    ensure_builtin_tools_loaded()
    return tuple(_builtin_tool_classes_by_name.values())


__all__ = [
    "builtin_tool",
    "ensure_builtin_tools_loaded",
    "get_builtin_tool_class",
    "get_builtin_tool_name",
    "iter_builtin_tool_classes",
]
