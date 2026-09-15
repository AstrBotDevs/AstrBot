from dataclasses import dataclass, field

from astrbot.api import FunctionTool
from astrbot.core.tools.registry import (
    builtin_tool,
    register_builtin_tools_by_module_prefix,
    get_builtin_tool_class,
    get_builtin_tool_name,
    unregister_builtin_tools_by_module_prefix,
)


def _register_test_tool():
    @builtin_tool
    @dataclass
    class ExampleTool(FunctionTool):
        name: str = "astrbot_test_reload_tool"
        description: str = "Test tool for registry reload behavior."
        parameters: dict = field(
            default_factory=lambda: {"type": "object", "properties": {}}
        )

    return ExampleTool


def test_builtin_tool_registry_can_unregister_and_reregister_same_name():
    tool_cls_1 = _register_test_tool()
    registered = register_builtin_tools_by_module_prefix(__name__)

    assert registered == ["astrbot_test_reload_tool"]
    assert get_builtin_tool_class("astrbot_test_reload_tool") is tool_cls_1
    assert get_builtin_tool_name(tool_cls_1) == "astrbot_test_reload_tool"

    removed = unregister_builtin_tools_by_module_prefix(__name__)

    assert removed == ["astrbot_test_reload_tool"]
    assert get_builtin_tool_class("astrbot_test_reload_tool") is None
    assert get_builtin_tool_name(tool_cls_1) is None

    tool_cls_2 = _register_test_tool()
    assert tool_cls_2 is not tool_cls_1
    assert get_builtin_tool_class("astrbot_test_reload_tool") is tool_cls_2

    unregister_builtin_tools_by_module_prefix(__name__)
