"""Tests for _plugin_tool_fix function in astr_main_agent.py

This test file uses isolated unit tests to avoid circular import issues.
"""

import os
import sys

# 将项目根目录添加到 sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dataclasses import dataclass

# Import only the minimal dependencies needed for the test
from astrbot.core.agent.tool import FunctionTool, ToolSet


class MockMCPTool(FunctionTool):
    """Mock MCP tool for testing - simulates MCPTool behavior."""

    def __init__(
        self,
        name: str,
        server_name: str = "test_server",
        scopes: tuple[str, ...] | None = None,
    ):
        super().__init__(
            name=name,
            description=f"Mock MCP tool {name}",
            parameters={"type": "object", "properties": {}},
        )
        self.mcp_server_name = server_name
        self.mcp_server_scopes = scopes


class MockFunctionTool(FunctionTool):
    """Mock regular function tool for testing."""

    def __init__(self, name: str, handler_module_path: str | None = None):
        super().__init__(
            name=name,
            description=f"Mock tool {name}",
            parameters={"type": "object", "properties": {}},
        )
        self.handler_module_path = handler_module_path


@dataclass
class MockProviderRequest:
    """Mock ProviderRequest for testing."""

    func_tool: ToolSet | None = None


@dataclass
class MockPluginInfo:
    """Mock plugin info for testing."""

    name: str
    reserved: bool = False


@dataclass
class MockEvent:
    """Mock AstrMessageEvent for testing."""

    plugins_name: list[str] | None = None


def plugin_tool_fix_logic(
    event: MockEvent,
    req: MockProviderRequest,
    star_map: dict,
    llm_tools_func_list: list,
    inject_mcp: bool = True,
    agent_name: str = "main",
) -> None:
    """Implementation of _plugin_tool_fix logic for isolated testing.

    This is a copy of the actual function logic for testing purposes.
    """

    # Check if tool is MCPTool by checking for mcp_server_name attribute
    def is_mcp_tool(tool):
        return hasattr(tool, "mcp_server_name")

    def is_scope_allowed(tool):
        scopes = getattr(tool, "mcp_server_scopes", None)
        if scopes is None:
            return True
        if "*" in scopes:
            return True
        return agent_name in scopes

    if req.func_tool:
        filtered_tool_set = ToolSet()
        for tool in req.func_tool.tools:
            if is_mcp_tool(tool) and not is_scope_allowed(tool):
                continue
            filtered_tool_set.add_tool(tool)
        req.func_tool = filtered_tool_set

    if event.plugins_name is not None and req.func_tool:
        new_tool_set = ToolSet()
        for tool in req.func_tool.tools:
            if is_mcp_tool(tool):
                if is_scope_allowed(tool):
                    # 保留 MCP 工具
                    new_tool_set.add_tool(tool)
                continue
            mp = tool.handler_module_path
            if not mp:
                continue
            plugin = star_map.get(mp)
            if not plugin:
                continue
            if plugin.name in event.plugins_name or plugin.reserved:
                new_tool_set.add_tool(tool)
        req.func_tool = new_tool_set
    elif inject_mcp:
        # 仅在配置允许时注入 MCP 工具
        tool_set = req.func_tool
        if not tool_set:
            tool_set = ToolSet()
        for tool in llm_tools_func_list:
            if is_mcp_tool(tool) and is_scope_allowed(tool):
                tool_set.add_tool(tool)
        req.func_tool = tool_set


class TestPluginToolFix:
    """Test suite for _plugin_tool_fix function logic."""

    def test_inject_mcp_true_injects_tools(self):
        """When inject_mcp=True, MCP tools should be injected from global pool."""
        event = MockEvent(plugins_name=None)
        req = MockProviderRequest()
        req.func_tool = ToolSet()

        mcp_tool_1 = MockMCPTool("mcp_tool_1")
        mcp_tool_2 = MockMCPTool("mcp_tool_2")
        regular_tool = MockFunctionTool("regular_tool")
        llm_tools_list = [mcp_tool_1, mcp_tool_2, regular_tool]

        plugin_tool_fix_logic(event, req, {}, llm_tools_list, inject_mcp=True)

        # Should have injected MCP tools only
        assert len(req.func_tool.tools) == 2
        tool_names = {t.name for t in req.func_tool.tools}
        assert tool_names == {"mcp_tool_1", "mcp_tool_2"}

    def test_inject_mcp_false_skips_injection(self):
        """When inject_mcp=False, MCP tools should NOT be injected."""
        event = MockEvent(plugins_name=None)
        req = MockProviderRequest()
        req.func_tool = ToolSet()

        mcp_tool_1 = MockMCPTool("mcp_tool_1")
        mcp_tool_2 = MockMCPTool("mcp_tool_2")
        llm_tools_list = [mcp_tool_1, mcp_tool_2]

        plugin_tool_fix_logic(event, req, {}, llm_tools_list, inject_mcp=False)

        # Should NOT have any tools
        assert len(req.func_tool.tools) == 0

    def test_default_inject_mcp_is_true(self):
        """Default behavior (inject_mcp=True) should inject MCP tools."""
        event = MockEvent(plugins_name=None)
        req = MockProviderRequest()
        req.func_tool = ToolSet()

        mcp_tool = MockMCPTool("mcp_tool")
        llm_tools_list = [mcp_tool]

        # Call without inject_mcp parameter (should default to True)
        plugin_tool_fix_logic(event, req, {}, llm_tools_list)

        # Should have injected MCP tool
        assert len(req.func_tool.tools) == 1
        assert req.func_tool.tools[0].name == "mcp_tool"

    def test_plugins_name_set_filters_regular_tools(self):
        """When plugins_name is set, only tools from those plugins should be kept."""
        event = MockEvent(plugins_name=["plugin_a"])
        req = MockProviderRequest()

        # Create tools with different plugin associations
        tool_a = MockFunctionTool("tool_a", handler_module_path="plugins.plugin_a.main")
        tool_b = MockFunctionTool("tool_b", handler_module_path="plugins.plugin_b.main")
        mcp_tool = MockMCPTool("mcp_tool")

        req.func_tool = ToolSet([tool_a, tool_b, mcp_tool])

        star_map = {
            "plugins.plugin_a.main": MockPluginInfo("plugin_a"),
            "plugins.plugin_b.main": MockPluginInfo("plugin_b"),
        }

        plugin_tool_fix_logic(event, req, star_map, [], inject_mcp=True)

        # Should have tool_a (from plugin_a) and mcp_tool (always kept)
        tool_names = {t.name for t in req.func_tool.tools}
        assert tool_names == {"tool_a", "mcp_tool"}

    def test_reserved_plugins_always_included(self):
        """Tools from reserved plugins should always be included."""
        event = MockEvent(plugins_name=["plugin_a"])
        req = MockProviderRequest()

        tool_a = MockFunctionTool("tool_a", handler_module_path="plugins.plugin_a.main")
        tool_reserved = MockFunctionTool(
            "tool_reserved", handler_module_path="plugins.reserved.main"
        )

        req.func_tool = ToolSet([tool_a, tool_reserved])

        star_map = {
            "plugins.plugin_a.main": MockPluginInfo("plugin_a"),
            "plugins.reserved.main": MockPluginInfo("reserved", reserved=True),
        }

        plugin_tool_fix_logic(event, req, star_map, [], inject_mcp=True)

        tool_names = {t.name for t in req.func_tool.tools}
        assert tool_a.name in tool_names
        assert tool_reserved.name in tool_names

    def test_mcp_tools_preserved_in_plugins_name_mode(self):
        """MCP tools should be preserved even when plugins_name filtering is active."""
        event = MockEvent(plugins_name=["plugin_a"])
        req = MockProviderRequest()

        tool_a = MockFunctionTool("tool_a", handler_module_path="plugins.plugin_a.main")
        tool_b = MockFunctionTool("tool_b", handler_module_path="plugins.plugin_b.main")
        mcp_tool = MockMCPTool("mcp_tool")

        req.func_tool = ToolSet([tool_a, tool_b, mcp_tool])

        star_map = {
            "plugins.plugin_a.main": MockPluginInfo("plugin_a"),
            "plugins.plugin_b.main": MockPluginInfo("plugin_b"),
        }

        plugin_tool_fix_logic(event, req, star_map, [], inject_mcp=False)

        # MCP tool should be preserved, tool_b should be filtered out
        tool_names = {t.name for t in req.func_tool.tools}
        assert tool_names == {"tool_a", "mcp_tool"}

    def test_empty_tool_set_with_inject_mcp_false(self):
        """When func_tool is None and inject_mcp=False, should remain empty."""
        event = MockEvent(plugins_name=None)
        req = MockProviderRequest()
        req.func_tool = None

        mcp_tool = MockMCPTool("mcp_tool")
        llm_tools_list = [mcp_tool]

        plugin_tool_fix_logic(event, req, {}, llm_tools_list, inject_mcp=False)

        # Should be None
        assert req.func_tool is None

    def test_empty_tool_set_with_inject_mcp_true(self):
        """When func_tool is None and inject_mcp=True, should create ToolSet with MCP tools."""
        event = MockEvent(plugins_name=None)
        req = MockProviderRequest()
        req.func_tool = None

        mcp_tool = MockMCPTool("mcp_tool")
        llm_tools_list = [mcp_tool]

        plugin_tool_fix_logic(event, req, {}, llm_tools_list, inject_mcp=True)

        # Should have created ToolSet with MCP tool
        assert req.func_tool is not None
        assert len(req.func_tool.tools) == 1
        assert req.func_tool.tools[0].name == "mcp_tool"

    def test_mixed_tools_injection(self):
        """Test that only MCP tools are injected, not regular tools from global pool."""
        event = MockEvent(plugins_name=None)
        req = MockProviderRequest()
        req.func_tool = ToolSet()

        mcp_tool_1 = MockMCPTool("mcp_tool_1")
        mcp_tool_2 = MockMCPTool("mcp_tool_2")
        regular_tool_1 = MockFunctionTool("regular_tool_1")
        regular_tool_2 = MockFunctionTool("regular_tool_2")

        llm_tools_list = [mcp_tool_1, regular_tool_1, mcp_tool_2, regular_tool_2]

        plugin_tool_fix_logic(event, req, {}, llm_tools_list, inject_mcp=True)

        # Should only have MCP tools
        assert len(req.func_tool.tools) == 2
        tool_names = {t.name for t in req.func_tool.tools}
        assert tool_names == {"mcp_tool_1", "mcp_tool_2"}

    def test_scope_restricts_main_injection(self):
        """Main agent should only inject MCP tools visible to main scope."""
        event = MockEvent(plugins_name=None)
        req = MockProviderRequest()
        req.func_tool = ToolSet()

        main_tool = MockMCPTool("main_tool", scopes=("main",))
        sub_tool = MockMCPTool("sub_tool", scopes=("vrchat_agent",))
        all_tool = MockMCPTool("all_tool", scopes=("*",))
        llm_tools_list = [main_tool, sub_tool, all_tool]

        plugin_tool_fix_logic(
            event,
            req,
            {},
            llm_tools_list,
            inject_mcp=True,
            agent_name="main",
        )

        tool_names = {t.name for t in req.func_tool.tools}
        assert tool_names == {"main_tool", "all_tool"}

    def test_scope_filters_existing_mcp_tools(self):
        """Existing MCP tools should be filtered out when scope is not visible."""
        event = MockEvent(plugins_name=None)
        req = MockProviderRequest()
        req.func_tool = ToolSet(
            [
                MockMCPTool("visible", scopes=("main",)),
                MockMCPTool("hidden", scopes=("agent_x",)),
                MockFunctionTool("regular_tool", handler_module_path="plugins.a.main"),
            ]
        )

        plugin_tool_fix_logic(
            event,
            req,
            {},
            [],
            inject_mcp=False,
            agent_name="main",
        )

        tool_names = {t.name for t in req.func_tool.tools}
        assert tool_names == {"visible", "regular_tool"}
