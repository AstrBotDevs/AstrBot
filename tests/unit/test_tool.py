"""Unit tests for astrbot.core.agent.tool: FunctionTool, ToolSchema, ToolSet."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from jsonschema.exceptions import ValidationError

from astrbot.core.agent.tool import (
    FunctionTool,
    ToolSchema,
    ToolSet,
    ToolArgumentSpec,
    ToolExecResult,
)


class TestToolSchema:
    """ToolSchema construction and validation."""

    def test_tool_schema_minimal(self):
        """Construct with only name and description."""
        schema = ToolSchema(name="test_tool", description="A test tool")
        assert schema.name == "test_tool"
        assert schema.description == "A test tool"
        assert schema.parameters is None
        assert schema.active is True

    def test_tool_schema_with_parameters(self):
        """Construct with valid JSON Schema parameters."""
        params = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"],
        }
        schema = ToolSchema(name="search", description="Search tool", parameters=params)
        assert schema.name == "search"
        assert schema.parameters == params

    def test_tool_schema_invalid_parameters_raises(self):
        """Reject parameters that are not valid JSON Schema."""
        with pytest.raises(ValidationError):
            ToolSchema(
                name="bad",
                description="Bad schema",
                parameters={"type": "nonexistent"},
            )

    def test_tool_schema_inactive(self):
        """Explicitly set active=False."""
        schema = ToolSchema(name="off", description="Disabled", active=False)
        assert schema.active is False

    def test_tool_schema_parameters_none_allowed(self):
        """parameters=None is valid and passes validation."""
        schema = ToolSchema(name="no_params", description="No parameters", parameters=None)
        assert schema.parameters is None

    def test_tool_schema_empty_parameters_object(self):
        """Empty object parameters are valid JSON Schema."""
        schema = ToolSchema(
            name="empty",
            description="Empty params",
            parameters={"type": "object", "properties": {}},
        )
        assert schema.parameters == {"type": "object", "properties": {}}


class TestFunctionTool:
    """FunctionTool construction and call interface."""

    def test_function_tool_minimal(self):
        """Construct with minimal fields."""
        tool = FunctionTool(name="echo", description="Echo tool")
        assert tool.name == "echo"
        assert tool.description == "Echo tool"
        assert tool.handler is None
        assert tool.active is True
        assert tool.is_background_task is False
        assert tool.source == "plugin"

    def test_function_tool_with_handler(self):
        """Construct with an async handler."""
        async def handler(context, **kwargs):
            return "ok"
        tool = FunctionTool(
            name="greet",
            description="Greet",
            handler=handler,
            handler_module_path="tests.test_tool",
        )
        assert tool.handler is handler
        assert tool.handler_module_path == "tests.test_tool"

    def test_function_tool_background_task(self):
        """Construct with is_background_task=True."""
        tool = FunctionTool(
            name="bg",
            description="Background",
            is_background_task=True,
        )
        assert tool.is_background_task is True

    def test_function_tool_source_values(self):
        """Construct with different source values."""
        for source in ("plugin", "internal", "mcp"):
            tool = FunctionTool(
                name=f"tool_{source}",
                description=source,
                source=source,
            )
            assert tool.source == source

    def test_function_tool_repr(self):
        """__repr__ returns a meaningful string."""
        tool = FunctionTool(name="sum", description="Sum numbers")
        rep = repr(tool)
        assert "FuncTool" in rep
        assert "sum" in rep

    def test_function_tool_call_not_implemented(self):
        """call() raises NotImplementedError when no handler is set."""
        tool = FunctionTool(name="todo", description="Not implemented")
        with pytest.raises(NotImplementedError, match="FunctionTool.call"):
            import asyncio
            asyncio.run(tool.call(MagicMock()))

    def test_function_tool_with_parameters(self):
        """Construct with valid parameters."""
        params = {
            "type": "object",
            "properties": {"x": {"type": "integer"}},
        }
        tool = FunctionTool(name="add", description="Add", parameters=params)
        assert tool.parameters == params

    def test_function_tool_active_false(self):
        """Construct with active=False."""
        tool = FunctionTool(name="inactive_tool", description="Not active", active=False)
        assert tool.active is False

    def test_function_tool_inherits_validation(self):
        """FunctionTool inherits ToolSchema parameter validation."""
        with pytest.raises(ValidationError):
            FunctionTool(
                name="bad",
                description="Bad",
                parameters={"type": "madeup"},
            )


class TestToolSet:
    """ToolSet add/remove/get and serialization methods."""

    def test_empty_toolset(self):
        """New ToolSet is empty."""
        ts = ToolSet()
        assert ts.empty() is True
        assert len(ts) == 0
        assert bool(ts) is False

    def test_add_tool(self):
        """Add a tool increases length."""
        ts = ToolSet()
        tool = FunctionTool(name="a", description="Tool A")
        ts.add_tool(tool)
        assert len(ts) == 1
        assert ts.empty() is False
        assert bool(ts) is True

    def test_add_duplicate_name_overwrites(self):
        """Adding a tool with same name replaces the existing one."""
        ts = ToolSet()
        ts.add_tool(FunctionTool(name="dup", description="Original"))
        ts.add_tool(FunctionTool(name="dup", description="Replacement"))
        assert len(ts) == 1
        tool = ts.get_tool("dup")
        assert tool is not None
        assert tool.description == "Replacement"

    def test_add_duplicate_active_prefers_active(self):
        """When a duplicate is added, active=True wins over active=False."""
        ts = ToolSet()
        inactive = FunctionTool(name="x", description="Inactive", active=False)
        active = FunctionTool(name="x", description="Active", active=True)
        ts.add_tool(inactive)
        ts.add_tool(active)
        tool = ts.get_tool("x")
        assert tool is not None
        assert tool.description == "Active"

    def test_add_duplicate_inactive_does_not_replace_active(self):
        """Adding an inactive tool with an already active name does not overwrite."""
        ts = ToolSet()
        active = FunctionTool(name="y", description="Active", active=True)
        inactive = FunctionTool(name="y", description="Inactive", active=False)
        ts.add_tool(active)
        ts.add_tool(inactive)
        tool = ts.get_tool("y")
        assert tool is not None
        assert tool.description == "Active"

    def test_remove_tool(self):
        """Remove a tool by name."""
        ts = ToolSet()
        ts.add_tool(FunctionTool(name="keep", description="Keep"))
        ts.add_tool(FunctionTool(name="remove_me", description="Remove"))
        ts.remove_tool("remove_me")
        assert len(ts) == 1
        assert ts.get_tool("keep") is not None
        assert ts.get_tool("remove_me") is None

    def test_remove_nonexistent_tool(self):
        """Removing a non-existent tool does not raise."""
        ts = ToolSet()
        ts.add_tool(FunctionTool(name="a", description="A"))
        ts.remove_tool("nonexistent")
        assert len(ts) == 1

    def test_get_tool_returns_none_for_non_functiontool(self):
        """get_tool returns None when a ToolSchema (not FunctionTool) exists with that name."""
        ts = ToolSet()
        schema = ToolSchema(name="plain", description="Plain schema")
        ts.add_tool(schema)
        assert ts.get_tool("plain") is None

    def test_get_tool_returns_functiontool(self):
        """get_tool returns the FunctionTool when present."""
        ts = ToolSet()
        tool = FunctionTool(name="found", description="Found tool")
        ts.add_tool(tool)
        result = ts.get_tool("found")
        assert result is tool

    def test_normalize_sorts_by_name(self):
        """normalize() sorts tools alphabetically by name."""
        ts = ToolSet()
        ts.add_tool(FunctionTool(name="z", description="Z"))
        ts.add_tool(FunctionTool(name="a", description="A"))
        ts.add_tool(FunctionTool(name="m", description="M"))
        ts.normalize()
        assert [t.name for t in ts.tools] == ["a", "m", "z"]

    def test_names(self):
        """names() returns list of tool names."""
        ts = ToolSet()
        ts.add_tool(FunctionTool(name="a", description="A"))
        ts.add_tool(FunctionTool(name="b", description="B"))
        assert ts.names() == ["a", "b"]

    def test_func_list(self):
        """func_list only includes FunctionTool instances."""
        ts = ToolSet()
        ts.add_tool(FunctionTool(name="func", description="Func"))
        ts.add_tool(ToolSchema(name="plain", description="Plain"))
        assert len(ts.func_list) == 1
        assert ts.func_list[0].name == "func"

    def test_merge(self):
        """merge() combines tools from another ToolSet."""
        ts1 = ToolSet()
        ts1.add_tool(FunctionTool(name="a", description="A"))
        ts2 = ToolSet()
        ts2.add_tool(FunctionTool(name="b", description="B"))
        ts1.merge(ts2)
        assert len(ts1) == 2

    def test_iteration(self):
        """ToolSet is iterable and yields ToolSchema items."""
        ts = ToolSet()
        ts.add_tool(FunctionTool(name="a", description="A"))
        ts.add_tool(FunctionTool(name="b", description="B"))
        names = [t.name for t in ts]
        assert names == ["a", "b"]

    def test_get_light_tool_set(self):
        """get_light_tool_set returns tools with empty parameters and no handler."""
        params = {
            "type": "object",
            "properties": {"q": {"type": "string"}},
        }
        ts = ToolSet()
        ts.add_tool(FunctionTool(
            name="search", description="Search", parameters=params,
            handler=AsyncMock(),
        ))
        light = ts.get_light_tool_set()
        assert len(light) == 1
        light_tool = light.get_tool("search")
        assert light_tool is not None
        assert light_tool.description == "Search"
        assert light_tool.parameters == {"type": "object", "properties": {}}
        assert light_tool.handler is None

    def test_get_light_tool_skips_inactive(self):
        """get_light_tool_set skips inactive tools."""
        ts = ToolSet()
        ts.add_tool(FunctionTool(name="active", description="Active", active=True))
        ts.add_tool(FunctionTool(name="inactive", description="Inactive", active=False))
        light = ts.get_light_tool_set()
        assert light.names() == ["active"]

    def test_get_param_only_tool_set(self):
        """get_param_only_tool_set returns tools with empty description."""
        params = {
            "type": "object",
            "properties": {"x": {"type": "integer"}},
        }
        ts = ToolSet()
        ts.add_tool(FunctionTool(name="calc", description="Calc", parameters=params))
        param_only = ts.get_param_only_tool_set()
        assert len(param_only) == 1
        tool = param_only.get_tool("calc")
        assert tool is not None
        assert tool.description == ""
        assert tool.parameters == params

    def test_anthropic_schema(self):
        """anthropic_schema returns Anthropic-compatible format."""
        ts = ToolSet()
        params = {
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "required": ["x"],
        }
        ts.add_tool(FunctionTool(name="add", description="Add", parameters=params))
        schema = ts.anthropic_schema()
        assert len(schema) == 1
        assert schema[0]["name"] == "add"
        assert schema[0]["description"] == "Add"
        assert schema[0]["input_schema"]["properties"] == {"x": {"type": "integer"}}
        assert schema[0]["input_schema"]["required"] == ["x"]

    def test_google_schema(self):
        """google_schema returns Google GenAI-compatible format."""
        ts = ToolSet()
        params = {
            "type": "object",
            "properties": {"val": {"type": "number", "description": "A value"}},
        }
        ts.add_tool(FunctionTool(name="sqrt", description="Square root", parameters=params))
        schema = ts.google_schema()
        assert "function_declarations" in schema
        assert schema["function_declarations"][0]["name"] == "sqrt"
