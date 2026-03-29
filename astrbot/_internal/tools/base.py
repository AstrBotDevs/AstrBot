"""Base tool classes for AstrBot internal runtime.

This module provides the FunctionTool base class used by MCP tools
in the new internal architecture.
"""

import copy
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

    def __bool__(self) -> bool:
        return bool(self._tools)

    def __repr__(self) -> str:
        return f"ToolSet(namespace={self.namespace!r}, tools={self.list_tools()!r})"

    def __str__(self) -> str:
        return f"ToolSet({self.namespace}, {len(self)} tools)"

    def names(self) -> list[str]:
        """Get names of all tools in this set."""
        return [tool.name for tool in self.tools]

    def empty(self) -> bool:
        """Check if the tool set is empty."""
        return len(self) == 0

    def merge(self, other: "ToolSet") -> None:
        """Merge another ToolSet into this one."""
        for tool in other.tools:
            self.add(tool)

    def normalize(self) -> None:
        """Sort tools by name for deterministic serialization."""
        self._tools = dict(sorted(self._tools.items(), key=lambda x: x[0]))

    def get_light_tool_set(self) -> "ToolSet":
        """Return a light tool set with only name/description."""
        light_tools = []
        for tool in self.tools:
            if hasattr(tool, "active") and not tool.active:
                continue
            light_tools.append(
                FunctionTool(
                    name=tool.name,
                    description=tool.description,
                    parameters={"type": "object", "properties": {}},
                    handler=None,
                )
            )
        return ToolSet("default", light_tools)

    def get_param_only_tool_set(self) -> "ToolSet":
        """Return a tool set with name/parameters only (no description)."""
        param_tools = []
        for tool in self.tools:
            if hasattr(tool, "active") and not tool.active:
                continue
            params = (
                copy.deepcopy(tool.parameters)
                if tool.parameters
                else {"type": "object", "properties": {}}
            )
            param_tools.append(
                FunctionTool(
                    name=tool.name,
                    description="",
                    parameters=params,
                    handler=None,
                )
            )
        return ToolSet("default", param_tools)

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

    def anthropic_schema(self) -> list[dict]:
        """Convert tools to Anthropic API format."""
        result = []
        for tool in self.tools:
            input_schema: dict[str, Any] = {"type": "object"}
            if tool.parameters:
                input_schema["properties"] = tool.parameters.get("properties", {})
                input_schema["required"] = tool.parameters.get("required", [])
            tool_def: dict[str, Any] = {"name": tool.name, "input_schema": input_schema}
            if tool.description:
                tool_def["description"] = tool.description
            result.append(tool_def)
        return result

    def google_schema(self) -> dict:
        """Convert tools to Google GenAI API format."""

        def convert_schema(schema: dict) -> dict:
            supported_types = {
                "string",
                "number",
                "integer",
                "boolean",
                "array",
                "object",
                "null",
            }
            supported_formats = {
                "string": {"enum", "date-time"},
                "integer": {"int32", "int64"},
                "number": {"float", "double"},
            }

            if "anyOf" in schema:
                return {"anyOf": [convert_schema(s) for s in schema["anyOf"]]}

            result = {}
            origin_type = schema.get("type")
            target_type = origin_type

            if isinstance(origin_type, list):
                target_type = next((t for t in origin_type if t != "null"), "string")

            if target_type in supported_types:
                result["type"] = target_type
                if "format" in schema and schema["format"] in supported_formats.get(
                    result["type"], set()
                ):
                    result["format"] = schema["format"]
            else:
                result["type"] = "null"

            support_fields = {
                "title",
                "description",
                "enum",
                "minimum",
                "maximum",
                "maxItems",
                "minItems",
                "nullable",
                "required",
            }
            result.update({k: schema[k] for k in support_fields if k in schema})

            if "properties" in schema:
                properties = {}
                for key, value in schema["properties"].items():
                    prop_value = convert_schema(value)
                    if "default" in prop_value:
                        del prop_value["default"]
                    if "additionalProperties" in prop_value:
                        del prop_value["additionalProperties"]
                    properties[key] = prop_value
                if properties:
                    result["properties"] = properties

            if target_type == "array":
                items_schema = schema.get("items")
                if isinstance(items_schema, dict):
                    result["items"] = convert_schema(items_schema)
                else:
                    result["items"] = {"type": "string"}

            return result

        tools_list = []
        for tool in self.tools:
            d: dict[str, Any] = {"name": tool.name}
            if tool.description:
                d["description"] = tool.description
            if tool.parameters:
                d["parameters"] = convert_schema(tool.parameters)
            tools_list.append(d)

        declarations: dict[str, Any] = {}
        if tools_list:
            declarations["function_declarations"] = tools_list
        return declarations

    def get_func_desc_openai_style(self, omit_empty_parameter_field: bool = False):
        """Get tools in OpenAI function calling style (deprecated)."""
        return self.openai_schema(omit_empty_parameter_field)

    def get_func_desc_anthropic_style(self):
        """Get tools in Anthropic style (deprecated)."""
        return self.anthropic_schema()

    def get_func_desc_google_genai_style(self):
        """Get tools in Google GenAI style (deprecated)."""
        return self.google_schema()
