"""Tests for FunctionToolManager with new internal tools architecture."""

from astrbot.core.provider.func_tool_manager import FunctionToolManager
from astrbot.core.computer.computer_tool_provider import get_all_tools


def test_computer_tools_provider_returns_tools():
    """ComputerToolProvider should return a list of computer tools."""
    tools = get_all_tools()

    assert len(tools) > 0
    names = [t.name for t in tools]
    assert "astrbot_execute_shell" in names


def test_register_internal_tools_adds_tools_to_manager():
    """register_internal_tools should add computer tools to the manager."""
    manager = FunctionToolManager()

    # Should start empty
    assert manager.get_func("astrbot_execute_shell") is None

    # Register internal tools
    manager.register_internal_tools()

    # Should now have the shell tool
    tool = manager.get_func("astrbot_execute_shell")
    assert tool is not None
    assert tool.name == "astrbot_execute_shell"


def test_manager_func_list_starts_empty():
    """func_list should start empty in new architecture."""
    manager = FunctionToolManager()

    assert manager.func_list == []


def test_register_internal_tools_does_not_duplicate():
    """Calling register_internal_tools twice should not duplicate tools."""
    manager = FunctionToolManager()
    manager.register_internal_tools()

    first_tool = manager.get_func("astrbot_execute_shell")
    assert first_tool is not None

    # Register again
    manager.register_internal_tools()

    # Should still have the same tool (not duplicated)
    second_tool = manager.get_func("astrbot_execute_shell")
    assert second_tool is first_tool
