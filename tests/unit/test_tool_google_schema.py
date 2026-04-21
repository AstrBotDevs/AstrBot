from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Generic, TypeVar

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_MODULE_PATH = REPO_ROOT / "astrbot/core/agent/tool.py"


def load_tool_module():
    module_names = [
        "astrbot",
        "astrbot.core",
        "astrbot.core.agent",
        "astrbot.core.message",
        "astrbot.core.message.message_event_result",
        "astrbot.core.agent.run_context",
        "astrbot.core.agent.tool",
    ]
    missing = object()
    previous_modules = {name: sys.modules.get(name, missing) for name in module_names}

    package_names = [
        "astrbot",
        "astrbot.core",
        "astrbot.core.agent",
        "astrbot.core.message",
    ]
    try:
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
    finally:
        for name, previous_module in previous_modules.items():
            if previous_module is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous_module


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


def test_openai_schema_keeps_raw_parameter_fields_by_default():
    tool_module = load_tool_module()
    FunctionTool = tool_module.FunctionTool
    ToolSet = tool_module.ToolSet

    tool = FunctionTool(
        name="search_sources",
        description="Search sources by query.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query.",
                    "examples": ["astrbot"],
                }
            },
            "examples": [{"query": "astrbot"}],
        },
    )

    schema = ToolSet([tool]).openai_schema()
    parameters = schema[0]["function"]["parameters"]

    assert parameters["examples"] == [{"query": "astrbot"}]
    assert parameters["properties"]["query"]["examples"] == ["astrbot"]


def test_openai_schema_can_sanitize_gemini_parameter_fields():
    tool_module = load_tool_module()
    FunctionTool = tool_module.FunctionTool
    ToolSet = tool_module.ToolSet

    tool = FunctionTool(
        name="search_sources",
        description="Search sources by query.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query.",
                    "examples": ["astrbot"],
                    "default": "astrbot",
                },
                "filters": {
                    "type": "object",
                    "description": "Nested filters.",
                    "properties": {
                        "tag": {
                            "type": "string",
                            "examples": ["docs"],
                        }
                    },
                    "additionalProperties": False,
                },
                "items": {
                    "type": "array",
                    "description": "Search result items.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "examples": ["source-1"],
                            }
                        },
                    },
                },
            },
            "required": ["query"],
            "examples": [{"query": "astrbot"}],
            "additionalProperties": False,
        },
    )

    schema = ToolSet([tool]).openai_schema(gemini_compatible_schema=True)
    parameters = schema[0]["function"]["parameters"]

    assert "examples" not in parameters
    assert "additionalProperties" not in parameters
    assert "examples" not in parameters["properties"]["query"]
    assert "default" not in parameters["properties"]["query"]
    assert "additionalProperties" not in parameters["properties"]["filters"]
    assert "examples" not in parameters["properties"]["filters"]["properties"]["tag"]
    item_id = parameters["properties"]["items"]["items"]["properties"]["id"]
    assert "examples" not in item_id
