"""Base tool classes for AstrBot internal runtime.

This module provides the FunctionTool base class used by MCP tools
in the new internal architecture.
"""

from collections.abc import AsyncGenerator, Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from pydantic import model_validator

ParametersType = dict[str, Any]


@dataclass
class ToolSchema:
    """A class representing the schema of a tool for function calling."""

    name: str
    """The name of the tool."""

    description: str
    """The description of the tool."""

    parameters: ParametersType = field(default_factory=dict)
    """The parameters of the tool, in JSON Schema format."""

    @model_validator(mode="after")
    def validate_parameters(self) -> "ToolSchema":
        """Validate the parameters JSON schema."""
        import jsonschema

        jsonschema.validate(
            self.parameters, jsonschema.Draft202012Validator.META_SCHEMA
        )
        return self


@dataclass
class FunctionTool(ToolSchema):
    """A callable tool, for function calling."""

    handler: Callable[..., Awaitable[str | None] | AsyncGenerator[Any, None]] | None = (
        None
    )
    """a callable that implements the tool's functionality. It should be an async function."""

    handler_module_path: str | None = None
    """
    The module path of the handler function. This is empty when the origin is mcp.
    This field must be retained, as the handler will be wrapped in functools.partial during initialization,
    causing the handler's __module__ to be functools
    """

    active: bool = True
    """
    Whether the tool is active. This field is a special field for AstrBot.
    You can ignore it when integrating with other frameworks.
    """

    is_background_task: bool = False
    """
    Declare this tool as a background task. Background tasks return immediately
    with a task identifier while the real work continues asynchronously.
    """

    source: str = "mcp"
    """
    Origin of this tool: 'plugin' (from star plugins), 'internal' (AstrBot built-in),
    or 'mcp' (from MCP servers). Used by WebUI for display grouping.
    """

    def __repr__(self) -> str:
        return f"FuncTool(name={self.name}, parameters={self.parameters}, description={self.description})"

    async def call(self, **kwargs: Any) -> Any:
        """Run the tool with the given arguments. The handler field has priority."""
        raise NotImplementedError(
            "FunctionTool.call() must be implemented by subclasses or set a handler."
        )


class ToolSet:
    """
    A collection of FunctionTools grouped under a namespace.

    ToolSets allow organizing related tools together. The LLM sees tools
    as "namespace/tool_name" when calling.
    """

    def __init__(self, namespace: str, tools: list[FunctionTool] | None = None) -> None:
        self.namespace = namespace
        self._tools: dict[str, FunctionTool] = {}
        if tools:
            for tool in tools:
                self.add(tool)

    def add(self, tool: FunctionTool) -> None:
        """Add a tool to the set."""
        self._tools[tool.name] = tool

    def add_tool(self, tool: FunctionTool) -> None:
        """Add a tool to the set (alias for add())."""
        self.add(tool)

    def remove(self, name: str) -> FunctionTool | None:
        """Remove and return a tool by name."""
        return self._tools.pop(name, None)

    def remove_tool(self, name: str) -> None:
        """Remove a tool by its name."""
        self._tools.pop(name, None)

    def get(self, name: str) -> FunctionTool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_tool(self, name: str) -> FunctionTool | None:
        """Get a tool by name (alias for get)."""
        return self.get(name)

    def list_tools(self) -> list[FunctionTool]:
        """List all tools in this set."""
        return list(self._tools.values())

    def __iter__(self) -> Iterator[FunctionTool]:
        return iter(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)

    def merge(self, other: "ToolSet") -> None:
        """Merge another ToolSet into this one."""
        for tool in other.tools:
            self.add(tool)

    @property
    def tools(self) -> list[FunctionTool]:
        """List all tools in this set."""
        return list(self._tools.values())

    def openai_schema(
        self, omit_empty_parameter_field: bool = False
    ) -> list[dict[str, Any]]:
        """Convert tools to OpenAI API function calling schema format."""
        result: list[dict[str, Any]] = []
        for tool in self._tools.values():
            func_def: dict[str, Any] = {
                "type": "function",
                "function": {"name": tool.name},
            }
            if tool.description:
                func_def["function"]["description"] = tool.description

            if tool.parameters is not None:
                if (
                    tool.parameters.get("properties")
                ) or not omit_empty_parameter_field:
                    func_def["function"]["parameters"] = tool.parameters

            result.append(func_def)
        return result
