import copy
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any, Literal

import jsonschema
import mcp
from pydantic import Field, model_validator
from pydantic.dataclasses import dataclass

from astrbot.core.message.message_event_result import MessageEventResult

from .run_context import ContextWrapper

ParametersType = dict[str, Any]
ToolExecResult = str | mcp.types.CallToolResult
ToolParallelPolicy = Literal["unknown", "safe", "serial", "blocked"]


def get_tool_id(tool: Any) -> str:
    """Return a stable identity for an installed runtime tool.

    Tool names are not stable enough for persisted policy: plugins and MCP
    servers can replace a same-named tool between runtime generations.
    """
    server_name = getattr(tool, "mcp_server_name", None)
    if isinstance(server_name, str) and server_name:
        original_name = getattr(tool, "mcp_tool_name", tool.name)
        return f"mcp:{server_name}:{original_name}"

    handler_module_path = getattr(tool, "handler_module_path", None)
    if isinstance(handler_module_path, str) and handler_module_path:
        return f"plugin:{handler_module_path}:{tool.name}"

    wrapped = getattr(tool, "_wrapped", None)
    if wrapped is not None and wrapped is not tool:
        return get_tool_id(wrapped)

    tool_type = type(tool)
    return f"builtin:{tool_type.__module__}.{tool_type.__qualname__}:{tool.name}"


def get_parallel_blocked_reason(tool: Any) -> str | None:
    """Return why a tool cannot be enabled for concurrent execution."""
    if not getattr(tool, "active", True):
        return "Tool is inactive."
    wrapped = getattr(tool, "_wrapped", None)
    if wrapped is not None and wrapped is not tool:
        return get_parallel_blocked_reason(wrapped)
    if type(tool).__name__ == "HandoffTool":
        return "Handoff tools manage nested agent state and remain serial."
    if getattr(tool, "is_background_task", False):
        return "Background tools outlive the current call and remain serial."
    if getattr(tool, "name", None) in {"send_message_to_user", "send_poke_to_user"}:
        return "Direct-send tools have side effects and remain serial."
    if (
        not getattr(tool, "handler_module_path", None)
        and not getattr(tool, "mcp_server_name", None)
        and not type(tool).__module__.startswith("astrbot.")
    ):
        return "The tool source could not be verified."
    policy = getattr(tool, "parallel_policy", "unknown")
    if policy == "blocked":
        return "The tool explicitly disallows parallel execution."
    if policy == "serial":
        return "The tool explicitly requires serial execution."
    return None


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
    def validate_parameters(self) -> ToolSchema:
        jsonschema.validate(
            self.parameters, jsonschema.Draft202012Validator.META_SCHEMA
        )
        return self


@dataclass
class FunctionTool[TContext](ToolSchema):
    """A callable tool, for function calling."""

    handler: (
        Callable[..., Awaitable[str | None] | AsyncGenerator[MessageEventResult]] | None
    ) = None
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
    parallel_policy: ToolParallelPolicy = "unknown"
    """Whether this tool is suitable for concurrent execution.

    ``unknown`` is the conservative default. Runtime policy still requires
    explicit administrator opt-in, and hard-blocked tool types cannot be
    enabled through configuration.
    """

    required_actions: tuple[str, ...] = ()
    """Actions required at the shared execution boundary.

    Tool declarations must select an explicit capability. The executor adds
    execution-near classifications for sensitive builtin tool families. An
    undeclared third-party tool is denied at the execution boundary.
    """

    def __repr__(self) -> str:
        return (
            "FunctionTool("
            f"name={self.name}, parameters={self.parameters}, "
            f"description={self.description})"
        )

    async def call(
        self, context: ContextWrapper[TContext], **kwargs: Any
    ) -> ToolExecResult:
        """Run the tool with the given arguments. The handler field has priority."""
        raise NotImplementedError(
            "FunctionTool.call() must be implemented by subclasses or set a handler."
        )


@dataclass
class ToolSet:
    """A set of function tools that can be used in function calling.

    This class provides methods to add, remove, and retrieve tools, as well as
    convert the tools to different API formats (OpenAI, Anthropic, Google GenAI).
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
                    parameters=light_params,
                    description=tool.description,
                    handler=None,
                    parallel_policy=tool.parallel_policy,
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
                    parameters=params,
                    description="",
                    handler=None,
                    parallel_policy=tool.parallel_policy,
                )
            )
        return ToolSet(param_tools)

    @property
    def func_list(self) -> list[FunctionTool]:
        """Get the list of function tools."""
        return self.tools

    def openai_chat_completions_schema(
        self, omit_empty_parameter_field: bool = False
    ) -> list[dict]:
        """Convert tools to the Chat Completions function-tool format."""
        result = []
        # Stable ordering preserves prompt-cache prefixes for compatible providers.
        for tool in sorted(self.tools, key=lambda tool: tool.name):
            func_def = {"type": "function", "function": {"name": tool.name}}
            if tool.description:
                func_def["function"]["description"] = tool.description

            if tool.parameters is not None:
                if (
                    tool.parameters and tool.parameters.get("properties")
                ) or not omit_empty_parameter_field:
                    func_def["function"]["parameters"] = tool.parameters

            result.append(func_def)
        return result

    def openai_responses_schema(self) -> list[dict]:
        """Convert tools to the flat Responses function-tool format.

        Do not rewrite a plugin's JSON Schema to force strict mode. In
        particular, changing optional properties into required ones changes a
        tool's public contract. Responses can negotiate strict mode itself and
        falls back to non-strict tool calling when a schema is incompatible.
        """
        result: list[dict] = []
        for tool in self.tools:
            item: dict[str, Any] = {"type": "function", "name": tool.name}
            if tool.description:
                item["description"] = tool.description
            item["parameters"] = copy.deepcopy(
                tool.parameters or {"type": "object", "properties": {}}
            )
            result.append(item)
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

    def names(self) -> list[str]:
        """获取所有工具的名称列表"""
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
