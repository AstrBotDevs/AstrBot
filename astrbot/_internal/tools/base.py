"""Internal base tool definitions for AstrBot.

This module provides the core tool abstractions used throughout AstrBot,
including tool schemas, callable function tools, and tool sets for
managing multiple tools.
"""

from __future__ import annotations

import copy
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any, Generic

import jsonschema
import mcp
from pydantic import Field, model_validator
from pydantic.dataclasses import dataclass

from astrbot.core.agent.run_context import ContextWrapper, TContext
from astrbot.core.message.message_event_result import MessageEventResult

ParametersType = dict[str, Any]
ToolExecResult = str | mcp.types.CallToolResult


@dataclass
class ToolSchema:
    """A class representing the schema of a tool for function calling.

    ToolSchema defines the interface contract for a tool, including its
    name, description, and parameter specification in JSON Schema format.
    The parameters are validated against the JSON Schema Draft 2020-12.
    """

    name: str
    """The name of the tool."""

    description: str
    """The description of the tool."""

    parameters: ParametersType
    """The parameters of the tool, in JSON Schema format."""

    @model_validator(mode="after")
    def validate_parameters(self) -> ToolSchema:
        """Validate that parameters conform to JSON Schema Draft 2020-12."""
        jsonschema.validate(
            self.parameters, jsonschema.Draft202012Validator.META_SCHEMA
        )
        return self


@dataclass
class FunctionTool(ToolSchema, Generic[TContext]):
    """A callable tool, for function calling.

    FunctionTool represents an executable tool that can be called by the LLM.
    It extends ToolSchema with a handler callable that performs the actual
    tool execution. The handler should be an async function.

    Type Parameters:
        TContext: The context type for tool execution.

    Attributes:
        handler: The async callable that implements the tool's functionality.
        handler_module_path: Module path of the handler function for serialization.
        active: Whether the tool is active and should be used.
        is_background_task: Whether this tool runs as a background task.
        source: Origin of the tool ('plugin', 'internal', or 'mcp').
    """

    handler: (
        Callable[..., Awaitable[str | None] | AsyncGenerator[MessageEventResult, None]]
        | None
    ) = None
    """A callable that implements the tool's functionality. It should be an async function."""

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
    source: str = "plugin"
    """
    Origin of this tool: 'plugin' (from star plugins), 'internal' (AstrBot built-in),
    or 'mcp' (from MCP servers). Used by WebUI for display grouping.
    """

    def __repr__(self) -> str:
        return f"FuncTool(name={self.name}, parameters={self.parameters}, description={self.description})"

    async def call(
        self, context: ContextWrapper[TContext], **kwargs: Any
    ) -> ToolExecResult:
        """Run the tool with the given arguments. The handler field has priority.

        Raises:
            NotImplementedError: If no handler is set.
        """
        raise NotImplementedError(
            "FunctionTool.call() must be implemented by subclasses or set a handler."
        )


@dataclass
class ToolSet:
    """A set of function tools that can be used in function calling.

    This class provides methods to add, remove, and retrieve tools, as well as
    convert the tools to different API formats (OpenAI, Anthropic, Google GenAI).

    Tools can be added with add_tool(), which handles duplicate names by
    preferring active tools. The normalize() method sorts tools by name
    for deterministic serialization.
    """

    tools: list[FunctionTool] = Field(default_factory=list)

    def empty(self) -> bool:
        """Check if the tool set is empty."""
        return len(self.tools) == 0

    def add_tool(self, tool: FunctionTool) -> None:
        """Add a tool to the set.

        If a tool with the same name already exists:
        - Prefer the one that is active (active=True)
        - If both have the same active state, use the new one (overwrite)
        """
        for i, existing_tool in enumerate(self.tools):
            if existing_tool.name == tool.name:
                # Use getattr with a default of True for compatibility with tools
                # that may not define an `active` attribute (e.g., mocks).
                existing_active = bool(getattr(existing_tool, "active", True))
                new_active = bool(getattr(tool, "active", True))
                # Overwrite if new tool is active, or if existing tool is not active
                if new_active or not existing_active:
                    self.tools[i] = tool
                return
        self.tools.append(tool)

    def remove_tool(self, name: str) -> None:
        """Remove a tool by its name."""
        self.tools = [tool for tool in self.tools if tool.name != name]

    def normalize(self) -> None:
        """Sort tools by name for deterministic serialization.

        This ensures the serialized tool schema sent to the LLM is
        identical across requests regardless of registration/injection
        order, enabling LLM provider prefix cache hits.
        """
        self.tools.sort(key=lambda t: t.name)

    def get_tool(self, name: str) -> FunctionTool | None:
        """Get a tool by its name."""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    def get_light_tool_set(self) -> ToolSet:
        """Return a light tool set with only name/description."""
        light_tools = []
        for tool in self.tools:
            if hasattr(tool, "active") and not tool.active:
                continue
            light_params = {
                "type": "object",
                "properties": {},
            }
            light_tools.append(
                FunctionTool(
                    name=tool.name,
                    description=tool.description,
                    parameters=light_params,
                    handler=None,
                )
            )
        return ToolSet(light_tools)

    def get_param_only_tool_set(self) -> ToolSet:
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
        return ToolSet(param_tools)

    def add_func(
        self,
        name: str,
        func_args: list,
        desc: str,
        handler: Callable[..., Awaitable[Any]],
    ) -> None:
        """Add a function tool to the set.

        .. deprecated:: 4.0.0
            Use add_tool() instead.
        """
        params = {
            "type": "object",  # hard-coded here
            "properties": {},
        }
        for param in func_args:
            params["properties"][param["name"]] = {
                "type": param["type"],
                "description": param["description"],
            }
        _func = FunctionTool(
            name=name,
            parameters=params,
            description=desc,
            handler=handler,
        )
        self.add_tool(_func)

    def remove_func(self, name: str) -> None:
        """Remove a function tool by its name.

        .. deprecated:: 4.0.0
            Use remove_tool() instead.
        """
        self.remove_tool(name)

    def get_func(self, name: str) -> FunctionTool | None:
        """Get all function tools.

        .. deprecated:: 4.0.0
            Use get_tool() instead.
        """
        return self.get_tool(name)

    @property
    def func_list(self) -> list[FunctionTool]:
        """Get the list of function tools."""
        return self.tools

    def openai_schema(self, omit_empty_parameter_field: bool = False) -> list[dict]:
        """Convert tools to OpenAI API function calling schema format."""
        result = []
        for tool in self.tools:
            func_def: dict[str, Any] = {
                "type": "function",
                "function": {"name": tool.name},
            }
            if tool.description:
                func_def["function"]["description"] = tool.description

            if tool.parameters is not None:
                if (
                    tool.parameters and tool.parameters.get("properties")
                ) or not omit_empty_parameter_field:
                    func_def["function"]["parameters"] = tool.parameters  # type: ignore[index]

            result.append(func_def)
        return result

    def anthropic_schema(self) -> list[dict]:
        """Convert tools to Anthropic API format."""
        result = []
        for tool in self.tools:
            input_schema = {"type": "object"}
            if tool.parameters:
                input_schema["properties"] = tool.parameters.get("properties", {})
                input_schema["required"] = tool.parameters.get("required", [])
            tool_def = {"name": tool.name, "input_schema": input_schema}
            if tool.description:
                tool_def["description"] = tool.description
            result.append(tool_def)
        return result

    def google_schema(self) -> dict:
        """Convert tools to Google GenAI API format."""

        def convert_schema(schema: dict) -> dict:
            """Convert schema to Gemini API format."""
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

            # Avoid side effects by not modifying the original schema
            origin_type = schema.get("type")
            target_type = origin_type

            # Compatibility fix: Gemini API expects 'type' to be a string (enum),
            # but standard JSON Schema (MCP) allows lists (e.g. ["string", "null"]).
            # We fallback to the first non-null type.
            if isinstance(origin_type, list):
                target_type = next((t for t in origin_type if t != "null"), "string")

            if target_type in supported_types:
                result["type"] = target_type
                if "format" in schema and schema["format"] in supported_formats.get(
                    result["type"],
                    set(),
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
                    # see #5217
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
                    # Gemini requires array schemas to include an `items` schema.
                    # JSON Schema allows omitting it, so fall back to a permissive
                    # string item schema instead of emitting an invalid declaration.
                    result["items"] = {"type": "string"}

            return result

        tools = []
        for tool in self.tools:
            d: dict[str, Any] = {"name": tool.name}
            if tool.description:
                d["description"] = tool.description
            if tool.parameters:
                d["parameters"] = convert_schema(tool.parameters)
            tools.append(d)

        declarations = {}
        if tools:
            declarations["function_declarations"] = tools
        return declarations

    def get_func_desc_openai_style(self, omit_empty_parameter_field: bool = False):
        """Get OpenAI style function descriptions.

        .. deprecated:: 4.0.0
            Use openai_schema() instead.
        """
        return self.openai_schema(omit_empty_parameter_field)

    def get_func_desc_anthropic_style(self):
        """Get Anthropic style function descriptions.

        .. deprecated:: 4.0.0
            Use anthropic_schema() instead.
        """
        return self.anthropic_schema()

    def get_func_desc_google_genai_style(self):
        """Get Google GenAI style function descriptions.

        .. deprecated:: 4.0.0
            Use google_schema() instead.
        """
        return self.google_schema()

    def names(self) -> list[str]:
        """Get a list of all tool names."""
        return [tool.name for tool in self.tools]

    def merge(self, other: ToolSet) -> None:
        """Merge another ToolSet into this one."""
        for tool in other.tools:
            self.add_tool(tool)

    def __len__(self) -> int:
        return len(self.tools)

    def __bool__(self) -> bool:
        return len(self.tools) > 0

    def __iter__(self):
        return iter(self.tools)

    def __repr__(self) -> str:
        return f"ToolSet(tools={self.tools})"

    def __str__(self) -> str:
        return f"ToolSet(tools={self.tools})"
