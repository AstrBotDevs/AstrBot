from collections.abc import Awaitable, Callable
from typing import Any, Generic

import jsonschema
import mcp
from deprecated import deprecated
from pydantic import model_validator
from pydantic.dataclasses import dataclass

from .run_context import ContextWrapper, TContext

ParametersType = dict[str, Any]


@dataclass
class ToolSchema:
    """A class representing the schema of a tool for function calling."""

    name: str
    """The name of the tool."""

    description: str
    """The description of the tool."""

    parameters: ParametersType
    """The parameters of the tool, in JSON Schema format."""

    @model_validator(mode="after")
    def validate_parameters(self) -> "ToolSchema":
        jsonschema.validate(
            self.parameters, jsonschema.Draft202012Validator.META_SCHEMA
        )
        return self


@dataclass
class FunctionTool(ToolSchema, Generic[TContext]):
    """A callable tool, for function calling."""

    handler: Callable[..., Awaitable[Any]] | None = None
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

    def __repr__(self):
        return f"FuncTool(name={self.name}, parameters={self.parameters}, description={self.description})"

    def __dict__(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "parameters": self.parameters,
            "description": self.description,
            "active": self.active,
        }

    async def call(
        self, context: ContextWrapper[TContext], **kwargs
    ) -> str | mcp.types.CallToolResult:
        """Run the tool with the given arguments. The handler field has priority."""
        raise NotImplementedError(
            "FunctionTool.call() must be implemented by subclasses or set a handler."
        )


class ToolSet:
    """A set of function tools that can be used in function calling.

    This class provides methods to add, remove, and retrieve tools, as well as
    convert the tools to different API formats (OpenAI, Anthropic, Google GenAI).
    """

    def __init__(self, tools: list[FunctionTool] | None = None):
        self.tools: list[FunctionTool] = tools or []

    def empty(self) -> bool:
        """Check if the tool set is empty."""
        return len(self.tools) == 0

    def add_tool(self, tool: FunctionTool):
        """Add a tool to the set."""
        # 检查是否已存在同名工具
        for i, existing_tool in enumerate(self.tools):
            if existing_tool.name == tool.name:
                self.tools[i] = tool
                return
        self.tools.append(tool)

    def remove_tool(self, name: str):
        """Remove a tool by its name."""
        self.tools = [tool for tool in self.tools if tool.name != name]

    def get_tool(self, name: str) -> FunctionTool | None:
        """Get a tool by its name."""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    @deprecated(reason="Use add_tool() instead", version="4.0.0")
    def add_func(
        self,
        name: str,
        func_args: list,
        desc: str,
        handler: Callable[..., Awaitable[Any]],
    ):
        """Add a function tool to the set."""
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

    @deprecated(reason="Use remove_tool() instead", version="4.0.0")
    def remove_func(self, name: str):
        """Remove a function tool by its name."""
        self.remove_tool(name)

    @deprecated(reason="Use get_tool() instead", version="4.0.0")
    def get_func(self, name: str) -> FunctionTool | None:
        """Get all function tools."""
        return self.get_tool(name)

    @property
    def func_list(self) -> list[FunctionTool]:
        """Get the list of function tools."""
        return self.tools

    def openai_schema(self, omit_empty_parameter_field: bool = False) -> list[dict]:
        """Convert tools to OpenAI API function calling schema format."""
        result = []
        for tool in self.tools:
            func_def = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                },
            }

            if (
                tool.parameters and tool.parameters.get("properties")
            ) or not omit_empty_parameter_field:
                func_def["function"]["parameters"] = tool.parameters

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
            tool_def = {
                "name": tool.name,
                "description": tool.description,
                "input_schema": input_schema,
            }
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

            if "type" in schema and schema["type"] in supported_types:
                result["type"] = schema["type"]
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
                    properties[key] = prop_value

                if properties:
                    result["properties"] = properties

            if "items" in schema:
                result["items"] = convert_schema(schema["items"])

            return result

        tools = []
        for tool in self.tools:
            d: dict[str, Any] = {
                "name": tool.name,
                "description": tool.description,
            }
            if tool.parameters:
                d["parameters"] = convert_schema(tool.parameters)
            tools.append(d)

        declarations = {}
        if tools:
            declarations["function_declarations"] = tools
        return declarations

    @deprecated(reason="Use openai_schema() instead", version="4.0.0")
    def get_func_desc_openai_style(self, omit_empty_parameter_field: bool = False):
        return self.openai_schema(omit_empty_parameter_field)

    @deprecated(reason="Use anthropic_schema() instead", version="4.0.0")
    def get_func_desc_anthropic_style(self):
        return self.anthropic_schema()

    @deprecated(reason="Use google_schema() instead", version="4.0.0")
    def get_func_desc_google_genai_style(self):
        return self.google_schema()

    def names(self) -> list[str]:
        """获取所有工具的名称列表"""
        return [tool.name for tool in self.tools]

    def __len__(self):
        return len(self.tools)

    def __bool__(self):
        return len(self.tools) > 0

    def __iter__(self):
        return iter(self.tools)

    def __repr__(self):
        return f"ToolSet(tools={self.tools})"

    def __str__(self):
        return f"ToolSet(tools={self.tools})"
