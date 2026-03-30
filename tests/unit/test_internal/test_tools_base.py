"""Tests for astrbot._internal.tools.base module."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from astrbot._internal.tools.base import (
    FunctionTool,
    ToolSchema,
    ToolSet,
)

# =============================================================================
# ToolSchema Tests
# =============================================================================


class TestToolSchema:
    """Test suite for ToolSchema."""

    def test_valid_parameters_schema(self):
        """Valid JSON Schema parameters should pass validation."""
        schema = ToolSchema(
            name="test_tool",
            description="A test tool",
            parameters={
                "type": "object",
                "properties": {"arg": {"type": "string", "description": "An argument"}},
                "required": ["arg"],
            },
        )
        assert schema.name == "test_tool"
        assert schema.description == "A test tool"
        assert schema.parameters["type"] == "object"

    def test_empty_parameters(self):
        """Empty parameters dict should be valid."""
        schema = ToolSchema(name="test", description="test", parameters={})
        assert schema.parameters == {}

    def test_invalid_parameters_no_op(self):
        """NOTE: ToolSchema is a plain @dataclass, not a Pydantic BaseModel.
        The @model_validator decorator has no effect, so validation is dead code.
        This test documents the current (broken) behavior for coverage.
        """
        # This creates successfully because model_validator is a no-op on plain dataclass
        schema = ToolSchema(
            name="test",
            description="test",
            parameters={"type": "invalid_type_not_real"},
        )
        assert schema.parameters == {"type": "invalid_type_not_real"}
        """Parameters without type field should still be valid since jsonschema validates structure."""
        # Actually this should be valid - jsonschema validates the schema itself
        schema = ToolSchema(
            name="test",
            description="test",
            parameters={"type": "string"},
        )
        assert schema.parameters["type"] == "string"


# =============================================================================
# FunctionTool Tests
# =============================================================================


class TestFunctionTool:
    """Test suite for FunctionTool."""

    def test_basic_function_tool(self):
        """Basic tool creation with name, description, parameters."""
        tool = FunctionTool(
            name="my_tool",
            description="Does something useful",
            parameters={"type": "object", "properties": {}},
        )
        assert tool.name == "my_tool"
        assert tool.description == "Does something useful"
        assert tool.active is True
        assert tool.is_background_task is False
        assert tool.source == "mcp"

    def test_function_tool_with_handler(self):
        """Tool with an async handler."""
        handler = AsyncMock(return_value="result")

        async def async_gen(**kwargs):
            yield "chunk1"
            yield "chunk2"

        tool = FunctionTool(
            name="handler_tool",
            description="Tool with handler",
            parameters={},
            handler=handler,
        )
        assert tool.handler is handler

    def test_function_tool_with_handler_module_path(self):
        """Tool preserves handler_module_path."""
        tool = FunctionTool(
            name="path_tool",
            description="Tool with module path",
            parameters={},
            handler_module_path="mymodule.myfunction",
        )
        assert tool.handler_module_path == "mymodule.myfunction"

    def test_function_tool_active_flag(self):
        """Active flag can be set to False."""
        tool = FunctionTool(
            name="inactive",
            description="Not active",
            parameters={},
            active=False,
        )
        assert tool.active is False

    def test_function_tool_background_task_flag(self):
        """Background task flag can be set."""
        tool = FunctionTool(
            name="background",
            description="Background task",
            parameters={},
            is_background_task=True,
        )
        assert tool.is_background_task is True

    def test_function_tool_source_defaults_to_mcp(self):
        """Source defaults to 'mcp'."""
        tool = FunctionTool(name="t", description="t", parameters={})
        assert tool.source == "mcp"

    def test_function_tool_source_can_be_plugin_or_internal(self):
        """Source can be 'plugin' or 'internal'."""
        plugin_tool = FunctionTool(
            name="p", description="p", parameters={}, source="plugin"
        )
        internal_tool = FunctionTool(
            name="i", description="i", parameters={}, source="internal"
        )
        assert plugin_tool.source == "plugin"
        assert internal_tool.source == "internal"

    def test_function_tool_repr(self):
        """__repr__ returns correct string."""
        tool = FunctionTool(
            name="repr_tool",
            description="For repr test",
            parameters={"type": "object"},
        )
        r = repr(tool)
        assert "repr_tool" in r
        assert "parameters" in r
        assert "repr test" in r

    @pytest.mark.asyncio
    async def test_call_raises_not_implemented(self):
        """call() without handler raises NotImplementedError."""
        tool = FunctionTool(name="t", description="t", parameters={})
        with pytest.raises(NotImplementedError, match="must be implemented"):
            await tool.call(arg="value")


# =============================================================================
# ToolSet Tests
# =============================================================================


class TestToolSetConstruction:
    """Test ToolSet construction and basic operations."""

    def test_empty_toolset(self):
        """Empty ToolSet with namespace."""
        ts = ToolSet("my_namespace")
        assert ts.namespace == "my_namespace"
        assert len(ts) == 0
        assert ts.empty()

    def test_toolset_from_list(self):
        """ToolSet initialized with a list of tools."""
        tool1 = FunctionTool(name="tool1", description="First", parameters={})
        tool2 = FunctionTool(name="tool2", description="Second", parameters={})
        ts = ToolSet("ns", [tool1, tool2])
        assert len(ts) == 2
        assert not ts.empty()

    def test_toolset_with_duplicate_names(self):
        """Last tool with same name overwrites earlier one."""
        tool1 = FunctionTool(name="dup", description="First", parameters={})
        tool2 = FunctionTool(name="dup", description="Second", parameters={})
        ts = ToolSet("ns", [tool1, tool2])
        assert len(ts) == 1
        assert ts.get("dup").description == "Second"


class TestToolSetAddRemove:
    """Test ToolSet add/remove operations."""

    def test_add_tool(self):
        """add() puts tool in set."""
        ts = ToolSet("ns")
        tool = FunctionTool(name="add_test", description="Add test", parameters={})
        ts.add(tool)
        assert ts.get("add_test") is tool

    def test_add_tool_alias(self):
        """add_tool() is alias for add()."""
        ts = ToolSet("ns")
        tool = FunctionTool(name="alias_test", description="Alias test", parameters={})
        ts.add_tool(tool)
        assert ts.get("alias_test") is tool

    def test_remove_tool(self):
        """remove_tool() removes by name (void return)."""
        ts = ToolSet("ns")
        tool = FunctionTool(name="remove_me", description="Remove me", parameters={})
        ts.add(tool)
        ts.remove_tool("remove_me")
        assert ts.get("remove_me") is None

    def test_remove_method(self):
        """remove() removes and returns tool."""
        ts = ToolSet("ns")
        tool = FunctionTool(name="return_me", description="Return me", parameters={})
        ts.add(tool)
        result = ts.remove("return_me")
        assert result is tool
        assert ts.get("return_me") is None

    def test_remove_nonexistent(self):
        """remove() returns None for missing name."""
        ts = ToolSet("ns")
        result = ts.remove("does_not_exist")
        assert result is None

    def test_get_tool_alias(self):
        """get_tool() is alias for get()."""
        ts = ToolSet("ns")
        tool = FunctionTool(name="get_alias", description="Get alias", parameters={})
        ts.add(tool)
        assert ts.get_tool("get_alias") is tool


class TestToolSetIteration:
    """Test ToolSet iteration and length."""

    def test_len(self):
        """__len__ returns count."""
        ts = ToolSet("ns")
        assert len(ts) == 0
        ts.add(FunctionTool(name="a", description="a", parameters={}))
        assert len(ts) == 1
        ts.add(FunctionTool(name="b", description="b", parameters={}))
        assert len(ts) == 2

    def test_bool_true_when_has_tools(self):
        """__bool__ is True when tools exist."""
        ts = ToolSet("ns")
        assert not ts
        ts.add(FunctionTool(name="x", description="x", parameters={}))
        assert ts

    def test_iter(self):
        """__iter__ yields tools."""
        tool1 = FunctionTool(name="iter1", description="Iter 1", parameters={})
        tool2 = FunctionTool(name="iter2", description="Iter 2", parameters={})
        ts = ToolSet("ns", [tool1, tool2])
        tools = list(ts)
        assert tool1 in tools
        assert tool2 in tools

    def test_list_tools(self):
        """list_tools() returns all tools."""
        tool1 = FunctionTool(name="list1", description="List 1", parameters={})
        tool2 = FunctionTool(name="list2", description="List 2", parameters={})
        ts = ToolSet("ns", [tool1, tool2])
        assert len(ts.list_tools()) == 2

    def test_tools_property(self):
        """tools property returns list of tools."""
        tool = FunctionTool(name="prop", description="Prop", parameters={})
        ts = ToolSet("ns", [tool])
        assert tool in ts.tools

    def test_names(self):
        """names() returns list of tool names."""
        tool1 = FunctionTool(name="alpha", description="Alpha", parameters={})
        tool2 = FunctionTool(name="beta", description="Beta", parameters={})
        ts = ToolSet("ns", [tool1, tool2])
        assert set(ts.names()) == {"alpha", "beta"}

    def test_empty_method(self):
        """empty() returns True when no tools."""
        ts = ToolSet("ns")
        assert ts.empty()
        ts.add(FunctionTool(name="y", description="y", parameters={}))
        assert not ts.empty()


class TestToolSetRepr:
    """Test ToolSet string representations."""

    def test_repr(self):
        """__repr__ includes namespace and tools."""
        tool = FunctionTool(name="repr_t", description="R", parameters={})
        ts = ToolSet("repr_ns", [tool])
        r = repr(ts)
        assert "repr_ns" in r
        assert "repr_t" in r

    def test_str(self):
        """__str__ includes namespace and count."""
        ts = ToolSet("str_ns")
        assert "str_ns" in str(ts)
        assert "0 tools" in str(ts)
        ts.add(FunctionTool(name="s", description="s", parameters={}))
        assert "1 tools" in str(ts)


class TestToolSetMerge:
    """Test ToolSet merge and normalize."""

    def test_merge(self):
        """merge() adds all tools from another ToolSet."""
        ts1 = ToolSet("ns1")
        ts1.add(FunctionTool(name="keep", description="Keep", parameters={}))
        ts2 = ToolSet("ns2")
        ts2.add(FunctionTool(name="added", description="Added", parameters={}))
        ts1.merge(ts2)
        assert ts1.get("keep") is not None
        assert ts1.get("added") is not None
        assert len(ts1) == 2

    def test_merge_overwrites_duplicate(self):
        """merge() overwrites tools with same name."""
        ts1 = ToolSet("ns1")
        ts1.add(FunctionTool(name="dup", description="Original", parameters={}))
        ts2 = ToolSet("ns2")
        ts2.add(FunctionTool(name="dup", description="Merged", parameters={}))
        ts1.merge(ts2)
        assert ts1.get("dup").description == "Merged"

    def test_normalize_sorts_by_name(self):
        """normalize() sorts tools by name for deterministic output."""
        tool_c = FunctionTool(name="charlie", description="C", parameters={})
        tool_a = FunctionTool(name="alpha", description="A", parameters={})
        tool_b = FunctionTool(name="bravo", description="B", parameters={})
        ts = ToolSet("ns", [tool_c, tool_a, tool_b])
        ts.normalize()
        names = list(ts._tools.keys())
        assert names == ["alpha", "bravo", "charlie"]


class TestToolSetLightToolSet:
    """Test get_light_tool_set()."""

    def test_light_tool_set_excludes_inactive(self):
        """Inactive tools are excluded."""
        active = FunctionTool(
            name="active", description="Active", parameters={}, active=True
        )
        inactive = FunctionTool(
            name="inactive", description="Inactive", parameters={}, active=False
        )
        ts = ToolSet("ns", [active, inactive])
        light = ts.get_light_tool_set()
        assert light.get("active") is not None
        assert light.get("inactive") is None

    def test_light_tool_set_preserves_name_and_description(self):
        """Light tool set has name/description only."""
        tool = FunctionTool(
            name="light_test",
            description="Original description",
            parameters={"type": "object", "properties": {"x": {"type": "string"}}},
        )
        ts = ToolSet("ns", [tool])
        light = ts.get_light_tool_set()
        light_tool = light.get("light_test")
        assert light_tool.name == "light_test"
        assert light_tool.description == "Original description"
        assert light_tool.parameters == {"type": "object", "properties": {}}

    def test_light_tool_set_has_empty_handler(self):
        """Light tools have handler=None."""
        tool = FunctionTool(name="lh", description="LH", parameters={})
        ts = ToolSet("ns", [tool])
        light = ts.get_light_tool_set()
        assert light.get("lh").handler is None


class TestToolSetParamOnlyToolSet:
    """Test get_param_only_tool_set()."""

    def test_param_only_excludes_inactive(self):
        """Inactive tools are excluded."""
        active = FunctionTool(name="a", description="A", parameters={}, active=True)
        inactive = FunctionTool(name="i", description="I", parameters={}, active=False)
        ts = ToolSet("ns", [active, inactive])
        param = ts.get_param_only_tool_set()
        assert param.get("a") is not None
        assert param.get("i") is None

    def test_param_only_preserves_parameters(self):
        """Parameters are deep copied."""
        tool = FunctionTool(
            name="param_test",
            description="Keep this",
            parameters={"type": "object", "properties": {"x": {"type": "integer"}}},
        )
        ts = ToolSet("ns", [tool])
        param = ts.get_param_only_tool_set()
        param_tool = param.get("param_test")
        assert param_tool.parameters == {
            "type": "object",
            "properties": {"x": {"type": "integer"}},
        }
        assert param_tool.description == ""

    def test_param_only_empty_parameters_defaults(self):
        """Tools with no parameters get empty object schema."""
        tool = FunctionTool(name="no_params", description="No params", parameters=None)
        ts = ToolSet("ns", [tool])
        param = ts.get_param_only_tool_set()
        assert param.get("no_params").parameters == {"type": "object", "properties": {}}


# =============================================================================
# ToolSet Schema Tests - OpenAI
# =============================================================================


class TestToolSetOpenAISchema:
    """Test openai_schema()."""

    def test_empty_toolset(self):
        """Empty toolset returns empty list."""
        ts = ToolSet("ns")
        assert ts.openai_schema() == []

    def test_basic_openai_schema(self):
        """Basic tool converts to OpenAI format."""
        tool = FunctionTool(
            name="openai_tool",
            description="An OpenAI tool",
            parameters={"type": "object", "properties": {}},
        )
        ts = ToolSet("ns", [tool])
        schema = ts.openai_schema()
        assert len(schema) == 1
        assert schema[0]["type"] == "function"
        assert schema[0]["function"]["name"] == "openai_tool"
        assert schema[0]["function"]["description"] == "An OpenAI tool"
        assert "parameters" in schema[0]["function"]

    def test_openai_schema_no_description(self):
        """Tool without description omits description field."""
        tool = FunctionTool(name="nodesc", description="", parameters={})
        ts = ToolSet("ns", [tool])
        schema = ts.openai_schema()
        assert "description" not in schema[0]["function"]

    def test_openai_schema_omit_empty_parameters_true(self):
        """omit_empty_parameter_field=True removes empty parameters."""
        tool = FunctionTool(
            name="omit_empty",
            description="Test",
            parameters={"type": "object", "properties": {}},
        )
        ts = ToolSet("ns", [tool])
        schema = ts.openai_schema(omit_empty_parameter_field=True)
        assert "parameters" not in schema[0]["function"]

    def test_openai_schema_omit_empty_with_properties(self):
        """omit_empty=True but has properties -> keeps parameters."""
        tool = FunctionTool(
            name="keep_params",
            description="Test",
            parameters={"type": "object", "properties": {"x": {"type": "string"}}},
        )
        ts = ToolSet("ns", [tool])
        schema = ts.openai_schema(omit_empty_parameter_field=True)
        assert "parameters" in schema[0]["function"]

    def test_openai_schema_null_parameters(self):
        """Tool with parameters=None skips parameters field."""
        tool = FunctionTool(name="null_params", description="Test", parameters=None)
        ts = ToolSet("ns", [tool])
        schema = ts.openai_schema()
        # Since parameters is None, tool.parameters is None, so the condition
        # tool.parameters is not None is False, and omit_empty is False by default
        # so parameters should not be in the output
        assert "parameters" not in schema[0]["function"]


# =============================================================================
# ToolSet Schema Tests - Anthropic
# =============================================================================


class TestToolSetAnthropicSchema:
    """Test anthropic_schema()."""

    def test_empty_toolset(self):
        """Empty toolset returns empty list."""
        ts = ToolSet("ns")
        assert ts.anthropic_schema() == []

    def test_basic_anthropic_schema(self):
        """Basic tool converts to Anthropic format."""
        tool = FunctionTool(
            name="anthropic_tool",
            description="An Anthropic tool",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        )
        ts = ToolSet("ns", [tool])
        schema = ts.anthropic_schema()
        assert len(schema) == 1
        assert schema[0]["name"] == "anthropic_tool"
        assert schema[0]["description"] == "An Anthropic tool"
        assert schema[0]["input_schema"]["properties"] == {"query": {"type": "string"}}
        assert schema[0]["input_schema"]["required"] == ["query"]

    def test_anthropic_schema_no_parameters(self):
        """Tool with no parameters gets empty input_schema."""
        tool = FunctionTool(name="no_params", description="No params", parameters={})
        ts = ToolSet("ns", [tool])
        schema = ts.anthropic_schema()
        assert schema[0]["input_schema"] == {"type": "object"}

    def test_anthropic_schema_no_description(self):
        """Tool without description omits description field."""
        tool = FunctionTool(name="nodesc", description="", parameters={})
        ts = ToolSet("ns", [tool])
        schema = ts.anthropic_schema()
        assert "description" not in schema[0]


# =============================================================================
# ToolSet Schema Tests - Google GenAI
# =============================================================================


class TestToolSetGoogleSchema:
    """Test google_schema()."""

    def test_empty_toolset(self):
        """Empty toolset returns empty declarations."""
        ts = ToolSet("ns")
        assert ts.google_schema() == {}

    def test_basic_google_schema(self):
        """Basic tool converts to Google format."""
        tool = FunctionTool(
            name="google_tool",
            description="A Google tool",
            parameters={"type": "object", "properties": {}},
        )
        ts = ToolSet("ns", [tool])
        schema = ts.google_schema()
        assert "function_declarations" in schema
        assert len(schema["function_declarations"]) == 1
        decl = schema["function_declarations"][0]
        assert decl["name"] == "google_tool"
        assert decl["description"] == "A Google tool"

    def test_google_convert_any_of(self):
        """anyOf schemas are recursively converted."""
        tool = FunctionTool(
            name="anyof_tool",
            description="AnyOf test",
            parameters={
                "type": "object",
                "properties": {
                    "value": {
                        "anyOf": [
                            {"type": "string"},
                            {"type": "integer"},
                        ]
                    }
                },
            },
        )
        ts = ToolSet("ns", [tool])
        schema = ts.google_schema()
        props = schema["function_declarations"][0]["parameters"]["properties"]
        assert "anyOf" in props["value"]
        assert len(props["value"]["anyOf"]) == 2

    def test_google_convert_array_with_items(self):
        """Array types with items dict are converted."""
        tool = FunctionTool(
            name="array_tool",
            description="Array test",
            parameters={
                "type": "object",
                "properties": {
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                    }
                },
            },
        )
        ts = ToolSet("ns", [tool])
        schema = ts.google_schema()
        props = schema["function_declarations"][0]["parameters"]["properties"]
        assert props["tags"]["type"] == "array"
        assert props["tags"]["items"] == {"type": "string"}

    def test_google_convert_array_with_non_dict_items(self):
        """Array types with non-dict items default to string."""
        tool = FunctionTool(
            name="array_tool2",
            description="Array test 2",
            parameters={
                "type": "object",
                "properties": {"items": {"type": "array", "items": "not_a_dict"}},
            },
        )
        ts = ToolSet("ns", [tool])
        schema = ts.google_schema()
        props = schema["function_declarations"][0]["parameters"]["properties"]
        assert props["items"]["items"] == {"type": "string"}

    def test_google_unsupported_type_becomes_null(self):
        """Unsupported types become 'null'."""
        tool = FunctionTool(
            name="unsupported",
            description="Unsupported type",
            parameters={
                "type": "object",
                "properties": {"unknown": {"type": "unsupported_type_xyz"}},
            },
        )
        ts = ToolSet("ns", [tool])
        schema = ts.google_schema()
        props = schema["function_declarations"][0]["parameters"]["properties"]
        assert props["unknown"]["type"] == "null"

    def test_google_type_list_picks_non_null(self):
        """Type list like ['string', 'null'] picks 'string'."""
        tool = FunctionTool(
            name="nullable_str",
            description="Nullable string",
            parameters={
                "type": "object",
                "properties": {"name": {"type": ["string", "null"]}},
            },
        )
        ts = ToolSet("ns", [tool])
        schema = ts.google_schema()
        props = schema["function_declarations"][0]["parameters"]["properties"]
        assert props["name"]["type"] == "string"

    def test_google_removes_default_and_additional_props(self):
        """default and additionalProperties are removed during conversion.
        These fields survive convert_schema via support_fields (e.g. via 'description').
        """
        tool = FunctionTool(
            name="cleanup",
            description="Cleanup test",
            parameters={
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "description": "A field with default",
                        "default": "foo",
                    },
                },
            },
        )
        ts = ToolSet("ns", [tool])
        schema = ts.google_schema()
        field = schema["function_declarations"][0]["parameters"]["properties"]["field"]
        # description should be preserved, default should be removed
        assert field.get("description") == "A field with default"
        assert "default" not in field

    def test_google_supported_fields_preserved(self):
        """Supported fields like enum, minimum, maximum are preserved."""
        tool = FunctionTool(
            name="fields",
            description="Fields test",
            parameters={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["active", "inactive"],
                        "description": "Status field",
                    },
                    "count": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                    },
                    "items": {
                        "type": "array",
                        "maxItems": 10,
                        "minItems": 1,
                    },
                },
            },
        )
        ts = ToolSet("ns", [tool])
        schema = ts.google_schema()
        props = schema["function_declarations"][0]["parameters"]["properties"]
        assert props["status"]["enum"] == ["active", "inactive"]
        assert props["status"]["description"] == "Status field"
        assert props["count"]["minimum"] == 0
        assert props["count"]["maximum"] == 100
        assert props["items"]["maxItems"] == 10
        assert props["items"]["minItems"] == 1

    def test_google_format_fields(self):
        """Format fields are preserved for supported types."""
        tool = FunctionTool(
            name="format_test",
            description="Format test",
            parameters={
                "type": "object",
                "properties": {
                    "dt": {"type": "string", "format": "date-time"},
                    "enum_val": {"type": "string", "format": "enum"},
                    "int32": {"type": "integer", "format": "int32"},
                    "int64": {"type": "integer", "format": "int64"},
                    "float_val": {"type": "number", "format": "float"},
                    "double_val": {"type": "number", "format": "double"},
                },
            },
        )
        ts = ToolSet("ns", [tool])
        schema = ts.google_schema()
        props = schema["function_declarations"][0]["parameters"]["properties"]
        assert props["dt"]["format"] == "date-time"
        assert props["int32"]["format"] == "int32"
        assert props["int64"]["format"] == "int64"
        assert props["float_val"]["format"] == "float"
        assert props["double_val"]["format"] == "double"

    def test_google_unsupported_format_ignored(self):
        """Format not in supported list is ignored."""
        tool = FunctionTool(
            name="bad_format",
            description="Bad format",
            parameters={
                "type": "object",
                "properties": {
                    "bad": {"type": "string", "format": "unsupported-format-xyz"}
                },
            },
        )
        ts = ToolSet("ns", [tool])
        schema = ts.google_schema()
        props = schema["function_declarations"][0]["parameters"]["properties"]
        assert "format" not in props["bad"]


class TestToolSetDeprecatedSchemaMethods:
    """Test deprecated schema convenience methods."""

    def test_get_func_desc_openai_style(self):
        """get_func_desc_openai_style returns same as openai_schema."""
        tool = FunctionTool(name="dep_openai", description="Deprecated", parameters={})
        ts = ToolSet("ns", [tool])
        assert ts.get_func_desc_openai_style() == ts.openai_schema()

    def test_get_func_desc_openai_style_with_flag(self):
        """get_func_desc_openai_style passes omit_empty flag."""
        tool = FunctionTool(
            name="dep_omit",
            description="Omit",
            parameters={"type": "object", "properties": {}},
        )
        ts = ToolSet("ns", [tool])
        assert ts.get_func_desc_openai_style(
            omit_empty_parameter_field=True
        ) == ts.openai_schema(omit_empty_parameter_field=True)

    def test_get_func_desc_anthropic_style(self):
        """get_func_desc_anthropic_style returns same as anthropic_schema."""
        tool = FunctionTool(
            name="dep_anthropic", description="Anthropic", parameters={}
        )
        ts = ToolSet("ns", [tool])
        assert ts.get_func_desc_anthropic_style() == ts.anthropic_schema()

    def test_get_func_desc_google_genai_style(self):
        """get_func_desc_google_genai_style returns same as google_schema."""
        tool = FunctionTool(name="dep_google", description="Google", parameters={})
        ts = ToolSet("ns", [tool])
        assert ts.get_func_desc_google_genai_style() == ts.google_schema()
