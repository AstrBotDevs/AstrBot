from astrbot.core import sp
from astrbot.core.provider.func_tool_manager import FunctionToolManager
from astrbot.core.tools.computer_tools.shell import ExecuteShellTool
from astrbot.core.tools.message_tools import SendMessageToUserTool


def test_get_builtin_tool_by_class_returns_cached_instance():
    manager = FunctionToolManager()

    tool_by_class = manager.get_builtin_tool(SendMessageToUserTool)
    tool_by_name = manager.get_builtin_tool("send_message_to_user")

    assert tool_by_class is tool_by_name
    assert manager.get_func("send_message_to_user") is tool_by_class
    assert tool_by_class.name == "send_message_to_user"


def test_builtin_tool_ignores_inactivated_llm_tools():
    manager = FunctionToolManager()
    sp.put(
        "inactivated_llm_tools",
        ["send_message_to_user"],
        scope="global",
        scope_id="global",
    )

    try:
        tool = manager.get_builtin_tool(SendMessageToUserTool)
        assert tool.active is True
    finally:
        sp.put("inactivated_llm_tools", [], scope="global", scope_id="global")


def test_computer_tools_are_registered_as_builtin_tools():
    manager = FunctionToolManager()

    tool = manager.get_builtin_tool(ExecuteShellTool)

    assert tool.name == "astrbot_execute_shell"
    assert manager.is_builtin_tool("astrbot_execute_shell") is True
