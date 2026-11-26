"""Legacy FunctionTool class-form and ToolSet facades."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from ...tools import Tool, ToolParam
from .platform_events import build_legacy_event


@dataclass
class FunctionTool:
    """Legacy class-form tool base.

    Mirrors the in-core pydantic dataclass shape: plugins subclass it
    declaring ``name``, ``description`` and a JSON-schema ``parameters``
    dict, and implement ``call`` (legacy ``run`` is accepted here too; the
    new SDK itself only knows ``call``). Alternatively a plain ``handler``
    callable can be supplied, taking priority like in the old core.
    """

    name: str = ""
    description: str = ""
    parameters: dict = field(default_factory=dict)
    handler: Any = None
    handler_module_path: str | None = None
    active: bool = True

    def __class_getitem__(cls, item: Any) -> type:
        """Legacy FunctionTool[TContext] subscription is a no-op."""
        return cls

    async def call(self, context: Any, **kwargs: Any) -> Any:
        """Run the tool; subclasses implement this (or legacy ``run``)."""
        run = getattr(self, "run", None)
        if run is not None:
            return await run(context, **kwargs)
        raise NotImplementedError(
            "FunctionTool.call() must be implemented by subclasses"
        )


class ToolSet:
    """Legacy tool container passed as func_tool/tools arguments."""

    def __init__(self, tools: list | None = None) -> None:
        self.tools: list = list(tools or [])

    def empty(self) -> bool:
        return not self.tools

    def add_tool(self, tool: Any) -> None:
        for index, existing in enumerate(self.tools):
            if existing.name == tool.name:
                self.tools[index] = tool
                return
        self.tools.append(tool)

    def remove_tool(self, name: str) -> None:
        self.tools = [tool for tool in self.tools if tool.name != name]

    def get_tool(self, name: str) -> Any:
        return next((tool for tool in self.tools if tool.name == name), None)

    def names(self) -> list[str]:
        return [tool.name for tool in self.tools]


def _json_schema_params(schema: dict) -> tuple[ToolParam, ...]:
    """Convert one legacy JSON-schema parameters dict into ToolParams."""
    properties = schema.get("properties", {}) if schema else {}
    required = set(schema.get("required", [])) if schema else set()
    return tuple(
        ToolParam(
            name=name,
            type=str(spec.get("type", "string")),
            description=str(spec.get("description", "")),
            required=name in required,
        )
        for name, spec in properties.items()
    )


class LegacyFunctionToolAdapter(Tool):
    """Adapt one legacy FunctionTool instance onto the new Tool contract."""

    def __init__(self, legacy_tool: FunctionTool, context: Any) -> None:
        self.name = legacy_tool.name
        self.description = legacy_tool.description
        self.params = _json_schema_params(legacy_tool.parameters)
        self._legacy_tool = legacy_tool
        self._context = context

    async def call(self, call, **kwargs: Any) -> Any:
        """Invoke the legacy call(context, **kwargs) with a facade wrapper."""
        if self._legacy_tool.handler is not None:
            # A plain handler callable takes priority, like in the old core.
            result = self._legacy_tool.handler(**kwargs)
            if inspect.isawaitable(result):
                result = await result
            return result
        event = None
        if getattr(call, "event", None) is not None:
            event = build_legacy_event(call.event, self._context)
        agent_context = SimpleNamespace(event=event, context=self._context)
        wrapper = SimpleNamespace(context=agent_context)
        return await self._legacy_tool.call(wrapper, **kwargs)
