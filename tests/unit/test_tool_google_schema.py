from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Generic, TypeVar

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
