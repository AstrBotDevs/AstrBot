from dataclasses import dataclass
from deprecated import deprecated
from typing import Awaitable, Literal, Any, Optional
from .mcp_client import MCPClient


@dataclass
class FunctionTool:
    """A class representing a function tool that can be used in function calling."""

    name: str | None = None
    parameters: dict | None = None
    description: str | None = None
    handler: Awaitable | None = None
    """处理函数, 当 origin 为 mcp 时，这个为空"""
    handler_module_path: str | None = None
    """处理函数的模块路径，当 origin 为 mcp 时，这个为空

    必须要保留这个字段, handler 在初始化会被 functools.partial 包装，导致 handler 的 __module__ 为 functools
    """
    active: bool = True
    """是否激活"""

    origin: Literal["local", "mcp"] = "local"
    """函数工具的来源, local 为本地函数工具, mcp 为 MCP 服务"""

    # MCP 相关字段
    mcp_server_name: str | None = None
    """MCP 服务名称，当 origin 为 mcp 时有效"""
    mcp_client: MCPClient | None = None
    """MCP 客户端，当 origin 为 mcp 时有效"""

    def __repr__(self):
        return f"FuncTool(name={self.name}, parameters={self.parameters}, description={self.description}, active={self.active}, origin={self.origin})"

    def __dict__(self) -> dict[str, Any]:
        """将 FunctionTool 转换为字典格式"""
        return {
            "name": self.name,
            "parameters": self.parameters,
            "description": self.description,
            "active": self.active,
            "origin": self.origin,
            "mcp_server_name": self.mcp_server_name,
        }


class ToolSet:
    """A set of function tools that can be used in function calling.

    This class provides methods to add, remove, and retrieve tools, as well as
    convert the tools to different API formats (OpenAI, Anthropic, Google GenAI)."""

    def __init__(self, tools: list[FunctionTool] = None):
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

    def get_tool(self, name: str) -> Optional[FunctionTool]:
        """Get a tool by its name."""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    @deprecated(reason="Use add_tool() instead", version="4.0.0")
    def add_func(self, name: str, func_args: list, desc: str, handler: Awaitable):
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
    def get_func(self, name: str) -> list[FunctionTool]:
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

            if tool.parameters.get("properties") or not omit_empty_parameter_field:
                func_def["function"]["parameters"] = tool.parameters

            result.append(func_def)
        return result

    def anthropic_schema(self) -> list[dict]:
        """Convert tools to Anthropic API format."""
        result = []
        for tool in self.tools:
            tool_def = {
                "name": tool.name,
                "description": tool.description,
                "input_schema": {
                    "type": "object",
                    "properties": tool.parameters.get("properties", {}),
                    "required": tool.parameters.get("required", []),
                },
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
                    properties[key] = prop_value

                if properties:
                    result["properties"] = properties

            if "items" in schema:
                result["items"] = convert_schema(schema["items"])

            return result

        tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": convert_schema(tool.parameters),
            }
            for tool in self.tools
        ]

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
