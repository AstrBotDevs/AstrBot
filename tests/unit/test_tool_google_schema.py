from __future__ import annotations

import copy
import importlib.util
import sys
import types
from pathlib import Path
from typing import Generic, TypeVar

import jsonschema
import pytest
from google.genai import types as genai_types

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_MODULE_PATH = REPO_ROOT / "astrbot/core/agent/tool.py"


def load_tool_module():
    package_names = [
        "astrbot",
        "astrbot.core",
        "astrbot.core.agent",
        "astrbot.core.message",
    ]
    for name in package_names:
        if name not in sys.modules:
            module = types.ModuleType(name)
            module.__path__ = []
            sys.modules[name] = module

    message_result_module = types.ModuleType(
        "astrbot.core.message.message_event_result"
    )
    message_result_module.MessageEventResult = type("MessageEventResult", (), {})
    sys.modules[message_result_module.__name__] = message_result_module

    run_context_module = types.ModuleType("astrbot.core.agent.run_context")
    run_context_module.TContext = TypeVar("TContext")

    class ContextWrapper(Generic[run_context_module.TContext]):
        pass

    run_context_module.ContextWrapper = ContextWrapper
    sys.modules[run_context_module.__name__] = run_context_module

    spec = importlib.util.spec_from_file_location(
        "astrbot.core.agent.tool", TOOL_MODULE_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_google_schema_fills_missing_array_items_with_string_schema():
    tool_module = load_tool_module()
    FunctionTool = tool_module.FunctionTool
    ToolSet = tool_module.ToolSet

    tool = FunctionTool(
        name="search_sources",
        description="Search sources by UUID.",
        parameters={
            "type": "object",
            "properties": {
                "source_uuids": {
                    "type": "array",
                    "description": "Optional list of source UUIDs.",
                }
            },
            "required": ["source_uuids"],
        },
    )

    schema = ToolSet([tool]).google_schema()
    source_uuids = schema["function_declarations"][0]["parameters"]["properties"][
        "source_uuids"
    ]

    assert source_uuids["type"] == "array"
    assert source_uuids["items"] == {"type": "string"}


def test_google_schema_keeps_enums_only_on_string_fields():
    tool_module = load_tool_module()
    FunctionTool = tool_module.FunctionTool
    ToolSet = tool_module.ToolSet

    tool = FunctionTool(
        name="list_items",
        description="List items.",
        parameters={
            "type": "object",
            "properties": {
                "page_size": {
                    "type": "integer",
                    "description": "Items per page.",
                    "enum": [10, 20, 50],
                },
                "strict": {"type": "boolean", "enum": [True]},
                "order": {"type": ["string", "null"], "enum": ["asc", "desc", None]},
            },
        },
    )

    schema = ToolSet([tool]).google_schema()
    properties = schema["function_declarations"][0]["parameters"]["properties"]

    assert properties["page_size"] == {
        "type": "integer",
        "description": "Items per page.\nAllowed values: 10, 20, 50",
    }
    assert properties["strict"] == {
        "type": "boolean",
        "description": "Allowed values: true",
    }
    assert properties["order"] == {
        "type": "string",
        "enum": ["asc", "desc"],
        "nullable": True,
    }
    assert tool.parameters["properties"]["page_size"]["enum"] == [10, 20, 50]
    # The Gemini SDK rejects non-string enum values when the request is built.
    genai_types.Tool(function_declarations=schema["function_declarations"])


def test_openai_schema_sorts_tools_by_name_without_mutating_toolset_order():
    tool_module = load_tool_module()
    FunctionTool = tool_module.FunctionTool
    ToolSet = tool_module.ToolSet

    toolset = ToolSet(
        [
            FunctionTool(
                name="zebra",
                description="Zebra tool.",
                parameters={"type": "object", "properties": {}},
            ),
            FunctionTool(
                name="alpha",
                description="Alpha tool.",
                parameters={"type": "object", "properties": {}},
            ),
            FunctionTool(
                name="middle",
                description="Middle tool.",
                parameters={"type": "object", "properties": {}},
            ),
        ]
    )

    schema = toolset.openai_schema()

    assert [tool["function"]["name"] for tool in schema] == [
        "alpha",
        "middle",
        "zebra",
    ]
    assert [tool.name for tool in toolset.tools] == ["zebra", "alpha", "middle"]


@pytest.mark.parametrize("value", ["unknown", 0, False, None, {"const": "data"}])
def test_openai_schema_converts_nested_const_without_mutating_parameters(value):
    tool_module = load_tool_module()
    parameters = {
        "type": "object",
        "properties": {
            "const": {"type": "string"},
            "time": {
                "oneOf": [
                    {
                        "type": "object",
                        "properties": {"kind": {"const": value}},
                    }
                ]
            },
            "items": {"type": "array", "items": {"const": value}},
        },
        "$defs": {"kind": {"const": value}},
        "default": {"const": "literal default"},
        "examples": [{"const": "literal example"}],
    }
    original = copy.deepcopy(parameters)
    tool = tool_module.FunctionTool(
        name="query", description="Query records.", parameters=parameters
    )

    result = tool_module.ToolSet([tool]).openai_schema()[0]["function"]["parameters"]

    assert result["properties"]["time"]["oneOf"][0]["properties"]["kind"] == {
        "enum": [value]
    }
    assert result["properties"]["items"]["items"] == {"enum": [value]}
    assert result["$defs"]["kind"] == {"enum": [value]}
    assert result["properties"]["const"] == {"type": "string"}
    assert result["default"] == original["default"]
    assert result["examples"] == original["examples"]
    assert tool.parameters == original
    jsonschema.Draft202012Validator.check_schema(result)


@pytest.mark.parametrize(
    ("constant", "enum"),
    [("a", ["a", "b"]), ("a", ["b"]), (True, [True, 1]), (1, [True, 1])],
)
def test_openai_schema_preserves_const_and_enum_intersection(constant, enum):
    tool_module = load_tool_module()
    tool = tool_module.FunctionTool(
        name="query",
        description="Query records.",
        parameters={
            "type": "object",
            "properties": {"kind": {"const": constant, "enum": enum}},
        },
    )

    result = tool_module.ToolSet([tool]).openai_schema()[0]["function"]["parameters"]

    assert "const" not in result["properties"]["kind"]
    for value in ("a", "b", True, 1, None):
        instance = {"kind": value}
        assert jsonschema.Draft202012Validator(result).is_valid(instance) == (
            jsonschema.Draft202012Validator(tool.parameters).is_valid(instance)
        )


@pytest.mark.parametrize(
    "keyword",
    [
        "allOf",
        "anyOf",
        "oneOf",
        "prefixItems",
        "items",
        "additionalProperties",
        "not",
        "if",
        "then",
        "else",
    ],
)
def test_openai_schema_converts_const_in_schema_keywords(keyword):
    tool_module = load_tool_module()
    child = {"const": "a"}
    nested = [child] if keyword in {"allOf", "anyOf", "oneOf", "prefixItems"} else child
    parameters = {"type": "object", "properties": {"value": {keyword: nested}}}
    tool = tool_module.FunctionTool(
        name="query", description="Query records.", parameters=parameters
    )

    result = tool_module.ToolSet([tool]).openai_schema()[0]["function"]["parameters"]

    expected = [{"enum": ["a"]}] if isinstance(nested, list) else {"enum": ["a"]}
    assert result["properties"]["value"][keyword] == expected
    assert tool.parameters == parameters


def test_openai_schema_keeps_other_provider_constraints_and_empty_parameter_option():
    tool_module = load_tool_module()
    tool = tool_module.FunctionTool(
        name="query",
        description="Query records.",
        parameters={"type": "object", "properties": {"kind": {"const": "a"}}},
    )
    toolset = tool_module.ToolSet([tool])
    toolset.openai_schema()
    assert toolset.anthropic_schema()[0]["input_schema"]["properties"]["kind"] == {
        "const": "a"
    }

    empty_tool = tool_module.FunctionTool(
        name="empty", description="No parameters.", parameters={}
    )
    empty_toolset = tool_module.ToolSet([empty_tool])
    assert "parameters" not in empty_toolset.openai_schema(True)[0]["function"]
    assert empty_toolset.openai_schema()[0]["function"]["parameters"] == {}
