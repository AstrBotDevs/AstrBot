"""Tests for tool conflict resolution in ToolSet.add_tool and FunctionToolManager.

This module tests the fix for issue #5821: when an MCP external tool shares a name
with a disabled built-in tool, the MCP tool should not be removed as collateral damage.
"""

import pytest

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.provider.func_tool_manager import FunctionToolManager


def make_tool(name: str, active: bool = True) -> FunctionTool:
    """Create a simple FunctionTool for testing."""
    return FunctionTool(
        name=name,
        description=f"Test tool {name}",
        parameters={"type": "object", "properties": {}},
        active=active,
    )


class TestToolSetAddTool:
    """Tests for ToolSet.add_tool conflict resolution."""

    def test_new_tool_active_existing_inactive_overwrites(self):
        """Active tool should overwrite inactive tool with same name."""
        toolset = ToolSet()
        toolset.add_tool(make_tool("web_search", active=False))
        toolset.add_tool(make_tool("web_search", active=True))

        assert len(toolset.tools) == 1
        assert toolset.tools[0].active is True

    def test_new_tool_inactive_existing_active_preserves_existing(self):
        """Inactive tool should NOT overwrite active tool with same name."""
        toolset = ToolSet()
        toolset.add_tool(make_tool("web_search", active=True))
        toolset.add_tool(make_tool("web_search", active=False))

        assert len(toolset.tools) == 1
        assert toolset.tools[0].active is True

    def test_both_active_last_one_wins(self):
        """When both tools are active, the new one should overwrite."""
        toolset = ToolSet()
        toolset.add_tool(make_tool("web_search", active=True))
        toolset.add_tool(make_tool("web_search", active=True))

        assert len(toolset.tools) == 1
        # The second tool should be the one kept
        assert toolset.tools[0].description == "Test tool web_search"

    def test_both_inactive_last_one_wins(self):
        """When both tools are inactive, the new one should overwrite."""
        toolset = ToolSet()
        toolset.add_tool(make_tool("web_search", active=False))
        toolset.add_tool(make_tool("web_search", active=False))

        assert len(toolset.tools) == 1

    def test_different_names_both_added(self):
        """Tools with different names should both be added."""
        toolset = ToolSet()
        toolset.add_tool(make_tool("web_search"))
        toolset.add_tool(make_tool("code_search"))

        assert len(toolset.tools) == 2

    def test_missing_active_attribute_defaults_to_true(self):
        """Tools without 'active' attribute should be treated as active."""
        toolset = ToolSet()

        # Create a mock object without 'active' attribute
        class MockTool:
            name = "mock_tool"
            description = "Mock"
            parameters = {"type": "object"}

        mock_tool = MockTool()
        toolset.add_tool(mock_tool)  # type: ignore

        # Should be added successfully
        assert len(toolset.tools) == 1

        # Adding another tool without active should overwrite
        mock_tool2 = MockTool()
        toolset.add_tool(mock_tool2)  # type: ignore

        assert len(toolset.tools) == 1


class TestFunctionToolManagerGetFunc:
    """Tests for FunctionToolManager.get_func with conflict resolution."""

    def test_returns_last_active_tool(self):
        """Should return the last active tool when multiple have same name."""
        manager = FunctionToolManager()
        manager.func_list = [
            make_tool("web_search", active=True),
            make_tool("web_search", active=True),
        ]

        result = manager.get_func("web_search")
        assert result is not None
        # Should return the last one (reversed order)
        assert result is manager.func_list[1]

    def test_returns_active_over_inactive(self):
        """Should prefer active tool over inactive tool with same name."""
        manager = FunctionToolManager()
        manager.func_list = [
            make_tool("web_search", active=False),
            make_tool("web_search", active=True),
        ]

        result = manager.get_func("web_search")
        assert result is not None
        assert result.active is True
        assert result is manager.func_list[1]

    def test_inactive_cannot_override_active(self):
        """Inactive tool after active should not be returned."""
        manager = FunctionToolManager()
        manager.func_list = [
            make_tool("web_search", active=True),
            make_tool("web_search", active=False),
        ]

        result = manager.get_func("web_search")
        assert result is not None
        assert result.active is True
        assert result is manager.func_list[0]

    def test_fallback_to_last_when_none_active(self):
        """Should return last tool with matching name when none are active."""
        manager = FunctionToolManager()
        manager.func_list = [
            make_tool("web_search", active=False),
            make_tool("web_search", active=False),
        ]

        result = manager.get_func("web_search")
        assert result is not None
        # Should return the last one (reversed order in fallback)
        assert result is manager.func_list[1]

    def test_returns_none_when_not_found(self):
        """Should return None when tool name not found."""
        manager = FunctionToolManager()
        manager.func_list = [make_tool("other_tool")]

        result = manager.get_func("web_search")
        assert result is None


class TestFunctionToolManagerGetFullToolSet:
    """Tests for FunctionToolManager.get_full_tool_set."""

    def test_deduplicates_by_name_using_add_tool(self):
        """Should deduplicate tools using add_tool logic."""
        manager = FunctionToolManager()
        manager.func_list = [
            make_tool("web_search", active=False),
            make_tool("web_search", active=True),
            make_tool("code_search", active=True),
        ]

        toolset = manager.get_full_tool_set()

        # Should have 2 tools after deduplication
        assert len(toolset.tools) == 2
        # web_search should be active (the MCP version)
        web_search = toolset.get_tool("web_search")
        assert web_search is not None
        assert web_search.active is True

    def test_no_deepcopy_preserves_identity(self):
        """Should not deep copy tools, preserving object identity."""
        manager = FunctionToolManager()
        tool = make_tool("web_search")
        manager.func_list = [tool]

        toolset = manager.get_full_tool_set()

        # Same object reference (no deepcopy)
        assert toolset.tools[0] is tool

    def test_mcp_tool_overrides_disabled_builtin(self):
        """
        Integration test: MCP tool should override disabled built-in tool.
        This is the core scenario for issue #5821.
        """
        manager = FunctionToolManager()
        # Simulate: built-in tool registered first (disabled)
        # Then MCP tool registered (enabled)
        manager.func_list = [
            make_tool("web_search", active=False),  # Built-in, disabled
            make_tool("web_search", active=True),  # MCP, enabled
        ]

        # get_func should return the MCP tool (active one)
        result = manager.get_func("web_search")
        assert result is not None
        assert result.active is True
        assert result is manager.func_list[1]

        # get_full_tool_set should also keep the MCP tool
        toolset = manager.get_full_tool_set()
        assert len(toolset.tools) == 1
        assert toolset.tools[0].active is True

    def test_disabled_mcp_cannot_override_enabled_builtin(self):
        """Disabled MCP tool should not override enabled built-in tool."""
        manager = FunctionToolManager()
        manager.func_list = [
            make_tool("web_search", active=True),  # Built-in, enabled
            make_tool("web_search", active=False),  # MCP, disabled
        ]

        result = manager.get_func("web_search")
        assert result is not None
        assert result.active is True
        assert result is manager.func_list[0]

        toolset = manager.get_full_tool_set()
        assert len(toolset.tools) == 1
        assert toolset.tools[0].active is True
