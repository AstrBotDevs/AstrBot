"""Tests for ToolCatalog -- immutable tool partitioning (CAT-01, CAT-02, CAT-03)."""

from unittest.mock import MagicMock

from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.mcp_client import MCPTool
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.tools.tool_catalog import ToolCatalog

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "always_loaded_tools": [],
    "auto_always_load_builtin": True,
}


def _make_tool(
    name: str,
    *,
    handler_module_path: str | None = None,
    active: bool = True,
) -> FunctionTool:
    """Create a minimal FunctionTool for testing."""
    return FunctionTool(
        name=name,
        description=f"Description for {name}",
        parameters={"type": "object", "properties": {}},
        handler_module_path=handler_module_path,
        active=active,
    )


def _make_handoff(name: str) -> HandoffTool:
    """Create a HandoffTool with a mocked Agent."""
    agent = MagicMock()
    agent.name = name
    return HandoffTool(agent=agent)


def _make_mcp_tool(name: str) -> MCPTool:
    """Create an MCPTool with mocked MCP dependencies."""
    mcp_tool = MagicMock()
    mcp_tool.name = name
    mcp_tool.description = f"MCP tool {name}"
    mcp_tool.inputSchema = {"type": "object", "properties": {}}
    mcp_client = MagicMock()
    return MCPTool(mcp_tool=mcp_tool, mcp_client=mcp_client, mcp_server_name="test-server")


# ===========================================================================
# CAT-01: Immutable snapshot
# ===========================================================================


class TestCatalogImmutableSnapshot:
    """CAT-01: ToolCatalog is an immutable snapshot of partitioned tools."""

    def test_catalog_from_tool_set(self):
        """from_tool_set returns a ToolCatalog with core_tools and deferred_tools as tuples."""
        ts = ToolSet(tools=[_make_tool("alpha"), _make_tool("beta")])
        catalog = ToolCatalog.from_tool_set(ts, DEFAULT_CONFIG)

        assert isinstance(catalog.core_tools, tuple)
        assert isinstance(catalog.deferred_tools, tuple)
        # With auto_always_load_builtin=True, both builtin tools should be core
        assert len(catalog.core_tools) == 2
        assert len(catalog.deferred_tools) == 0

    def test_catalog_immutable(self):
        """Assigning to catalog.core_tools raises FrozenInstanceError."""
        ts = ToolSet(tools=[_make_tool("alpha")])
        catalog = ToolCatalog.from_tool_set(ts, DEFAULT_CONFIG)

        # pydantic frozen dataclass raises FrozenInstanceError on assignment
        with __import__("pytest").raises(Exception, match="frozen"):
            catalog.core_tools = ()  # type: ignore[misc]

    def test_source_toolset_unchanged(self):
        """After catalog construction, tool_set.tools list is identical."""
        tools = [_make_tool("alpha"), _make_tool("beta")]
        ts = ToolSet(tools=list(tools))  # copy the list
        original_len = len(ts.tools)
        original_refs = list(ts.tools)

        ToolCatalog.from_tool_set(ts, DEFAULT_CONFIG)

        assert len(ts.tools) == original_len
        assert ts.tools == original_refs

    def test_get_tool_by_name(self):
        """catalog.get_tool returns the correct FunctionTool; None for nonexistent."""
        tool_a = _make_tool("alpha")
        tool_b = _make_tool("beta", handler_module_path="some.module")
        ts = ToolSet(tools=[tool_a, tool_b])
        catalog = ToolCatalog.from_tool_set(ts, DEFAULT_CONFIG)

        assert catalog.get_tool("alpha") is tool_a
        assert catalog.get_tool("beta") is tool_b
        assert catalog.get_tool("nonexistent") is None

    def test_all_tools_property(self):
        """catalog.all_tools returns core_tools + deferred_tools concatenated."""
        tool_a = _make_tool("alpha")  # builtin -> core
        tool_b = _make_tool("beta", handler_module_path="some.module")  # plugin -> deferred
        ts = ToolSet(tools=[tool_a, tool_b])
        catalog = ToolCatalog.from_tool_set(ts, DEFAULT_CONFIG)

        all_tools = catalog.all_tools
        assert isinstance(all_tools, tuple)
        assert len(all_tools) == 2
        # core first, then deferred
        assert all_tools == catalog.core_tools + catalog.deferred_tools

    def test_len(self):
        """len(catalog) equals len(core_tools) + len(deferred_tools)."""
        tool_a = _make_tool("alpha")
        tool_b = _make_tool("beta", handler_module_path="some.module")
        ts = ToolSet(tools=[tool_a, tool_b])
        catalog = ToolCatalog.from_tool_set(ts, DEFAULT_CONFIG)

        assert len(catalog) == len(catalog.core_tools) + len(catalog.deferred_tools)
        assert len(catalog) == 2


# ===========================================================================
# CAT-02: Partition logic
# ===========================================================================


class TestCatalogPartitionLogic:
    """CAT-02: Tools are correctly classified as core or deferred."""

    def test_handoff_tool_is_core(self):
        """A HandoffTool is always in core_tools regardless of other settings."""
        handoff = _make_handoff("helper")
        ts = ToolSet(tools=[handoff])
        catalog = ToolCatalog.from_tool_set(ts, DEFAULT_CONFIG)

        assert handoff in catalog.core_tools
        assert handoff not in catalog.deferred_tools

    def test_builtin_tool_is_core(self):
        """A FunctionTool with handler_module_path=None (not MCPTool) is core when auto_always_load_builtin=True."""
        tool = _make_tool("builtin_tool")
        ts = ToolSet(tools=[tool])
        catalog = ToolCatalog.from_tool_set(ts, DEFAULT_CONFIG)

        assert tool in catalog.core_tools
        assert tool not in catalog.deferred_tools

    def test_mcp_tool_is_deferred(self):
        """An MCPTool is in deferred_tools even when auto_always_load_builtin=True."""
        mcp = _make_mcp_tool("mcp_search")
        ts = ToolSet(tools=[mcp])
        catalog = ToolCatalog.from_tool_set(ts, DEFAULT_CONFIG)

        assert mcp in catalog.deferred_tools
        assert mcp not in catalog.core_tools

    def test_plugin_tool_is_deferred(self):
        """A FunctionTool with handler_module_path set is in deferred_tools."""
        tool = _make_tool("plugin_tool", handler_module_path="plugins.weather")
        ts = ToolSet(tools=[tool])
        catalog = ToolCatalog.from_tool_set(ts, DEFAULT_CONFIG)

        assert tool in catalog.deferred_tools
        assert tool not in catalog.core_tools

    def test_always_loaded_config(self):
        """A tool in always_loaded_tools config is core even if otherwise deferred."""
        tool = _make_tool("pinned_tool", handler_module_path="plugins.special")
        config = {
            "always_loaded_tools": ["pinned_tool"],
            "auto_always_load_builtin": True,
        }
        ts = ToolSet(tools=[tool])
        catalog = ToolCatalog.from_tool_set(ts, config)

        assert tool in catalog.core_tools
        assert tool not in catalog.deferred_tools

    def test_auto_builtin_disabled(self):
        """When auto_always_load_builtin=False, a builtin tool is deferred."""
        tool = _make_tool("builtin_tool")  # handler_module_path=None
        config = {
            "always_loaded_tools": [],
            "auto_always_load_builtin": False,
        }
        ts = ToolSet(tools=[tool])
        catalog = ToolCatalog.from_tool_set(ts, config)

        assert tool in catalog.deferred_tools
        assert tool not in catalog.core_tools

    def test_inactive_tools_excluded(self):
        """A FunctionTool with active=False appears in neither partition."""
        tool = _make_tool("inactive_tool", active=False)
        ts = ToolSet(tools=[tool])
        catalog = ToolCatalog.from_tool_set(ts, DEFAULT_CONFIG)

        assert tool not in catalog.core_tools
        assert tool not in catalog.deferred_tools
        assert len(catalog) == 0

    def test_overlap_harmless(self):
        """A tool matching both always_loaded AND builtin heuristic appears in core_tools exactly once."""
        tool = _make_tool("overlap_tool")  # builtin (handler_module_path=None)
        config = {
            "always_loaded_tools": ["overlap_tool"],
            "auto_always_load_builtin": True,
        }
        ts = ToolSet(tools=[tool])
        catalog = ToolCatalog.from_tool_set(ts, config)

        assert catalog.core_tools.count(tool) == 1
        assert tool not in catalog.deferred_tools


# ===========================================================================
# CAT-03: Deterministic ordering
# ===========================================================================


class TestCatalogDeterministicOrdering:
    """CAT-03: Tool ordering is deterministic and alphabetical."""

    def test_deterministic_ordering(self):
        """Constructing catalog from same ToolSet twice produces identical tuple ordering."""
        tools = [
            _make_tool("charlie"),
            _make_tool("alpha"),
            _make_tool("bravo", handler_module_path="plugins.bravo"),
        ]
        ts1 = ToolSet(tools=list(tools))
        ts2 = ToolSet(tools=list(tools))

        cat1 = ToolCatalog.from_tool_set(ts1, DEFAULT_CONFIG)
        cat2 = ToolCatalog.from_tool_set(ts2, DEFAULT_CONFIG)

        assert cat1.core_tools == cat2.core_tools
        assert cat1.deferred_tools == cat2.deferred_tools

    def test_alphabetical_ordering(self):
        """Tools within each partition are sorted alphabetically by tool.name."""
        tool_c = _make_tool("charlie")
        tool_a = _make_tool("alpha")
        tool_z = _make_tool("zulu", handler_module_path="plugins.zulu")
        tool_m = _make_tool("mike", handler_module_path="plugins.mike")

        ts = ToolSet(tools=[tool_c, tool_a, tool_z, tool_m])
        catalog = ToolCatalog.from_tool_set(ts, DEFAULT_CONFIG)

        core_names = [t.name for t in catalog.core_tools]
        deferred_names = [t.name for t in catalog.deferred_tools]

        assert core_names == sorted(core_names), f"Core not sorted: {core_names}"
        assert deferred_names == sorted(deferred_names), f"Deferred not sorted: {deferred_names}"

        # Verify specific expectations
        assert core_names == ["alpha", "charlie"]
        assert deferred_names == ["mike", "zulu"]
