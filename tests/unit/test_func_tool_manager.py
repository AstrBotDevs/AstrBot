from astrbot.core import sp
from astrbot.core.provider.func_tool_manager import FunctionToolManager
from astrbot.core.tools.message_tools import SendMessageToUserTool


def test_get_builtin_tool_by_class_returns_cached_instance():
    manager = FunctionToolManager()

    tool_by_class = manager.get_builtin_tool(SendMessageToUserTool)
    tool_by_name = manager.get_builtin_tool("send_message_to_user")

    assert tool_by_class is tool_by_name
    assert manager.get_func("send_message_to_user") is tool_by_class
    assert tool_by_class.name == "send_message_to_user"
