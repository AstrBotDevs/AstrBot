"""Tests for ToolsAssembler -- stateless tools parameter builder (ASM-01, ASM-02, ASM-03)."""

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.tools.discovery_state import DiscoveryState
from astrbot.core.tools.tool_catalog import ToolCatalog
from astrbot.core.tools.tools_assembler import ToolsAssembler

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


def _build_catalog(
    core_names: list[str],
    deferred_names: list[str],
) -> ToolCatalog:
    """Build a ToolCatalog with specific core and deferred tools.

    Core tools: builtin (no handler_module_path) with auto_always_load_builtin=True.
    Deferred tools: plugin tools (with handler_module_path set).
    """
    tools = []
    for name in core_names:
        tools.append(_make_tool(name))  # builtin -> core
    for name in deferred_names:
        tools.append(_make_tool(name, handler_module_path=f"plugins.{name}"))  # plugin -> deferred
    ts = ToolSet(tools=tools)
    return ToolCatalog.from_tool_set(ts, DEFAULT_CONFIG)


# ===========================================================================
# ASM-01: Assembly ordering
# ===========================================================================


class TestAssemblyOrdering:
    """ASM-01: build_tools() returns core + tool_search + discovered in order."""

    def test_ordering_core_search_discovered(self):
        """build_tools returns [core_a, core_b, tool_search, discovered_tool]."""
        catalog = _build_catalog(
            core_names=["core_a", "core_b"],
            deferred_names=["deferred_x", "deferred_y", "deferred_z"],
        )
        discovery_state = DiscoveryState()
        discovery_state.add("deferred_x")

        tool_search_tool = _make_tool("tool_search")

        result = ToolsAssembler.build_tools(catalog, discovery_state, tool_search_tool)

        names = [t.name for t in result.tools]
        assert names == ["core_a", "core_b", "tool_search", "deferred_x"]

    def test_no_tool_search_tool(self):
        """When tool_search_tool is None, no gap appears between core and discovered."""
        catalog = _build_catalog(
            core_names=["core_a", "core_b"],
            deferred_names=["deferred_x"],
        )
        discovery_state = DiscoveryState()
        discovery_state.add("deferred_x")

        result = ToolsAssembler.build_tools(catalog, discovery_state, tool_search_tool=None)

        names = [t.name for t in result.tools]
        assert names == ["core_a", "core_b", "deferred_x"]

    def test_discovered_in_discovery_order(self):
        """Discovered tools appear in discovery order, not alphabetical."""
        catalog = _build_catalog(
            core_names=["core_a"],
            deferred_names=["alpha", "beta"],
        )
        discovery_state = DiscoveryState()
        discovery_state.add("beta")
        discovery_state.add("alpha")

        tool_search_tool = _make_tool("tool_search")

        result = ToolsAssembler.build_tools(catalog, discovery_state, tool_search_tool)

        names = [t.name for t in result.tools]
        # beta was discovered first, then alpha -> discovery order preserved
        assert names == ["core_a", "tool_search", "beta", "alpha"]

    def test_missing_catalog_tool_skipped(self):
        """A discovered name not in catalog is silently skipped."""
        catalog = _build_catalog(
            core_names=["core_a"],
            deferred_names=["deferred_x"],
        )
        discovery_state = DiscoveryState()
        discovery_state.add("nonexistent")
        discovery_state.add("deferred_x")

        tool_search_tool = _make_tool("tool_search")

        result = ToolsAssembler.build_tools(catalog, discovery_state, tool_search_tool)

        names = [t.name for t in result.tools]
        # "nonexistent" silently skipped
        assert names == ["core_a", "tool_search", "deferred_x"]


# ===========================================================================
# ASM-02: Stable prefix
# ===========================================================================


class TestStablePrefix:
    """ASM-02: Prefix (core + tool_search) is identical across turns."""

    def test_prefix_identical_across_turns(self):
        """First N tools are identical object references regardless of discovery state."""
        catalog = _build_catalog(
            core_names=["core_a", "core_b"],
            deferred_names=["deferred_x", "deferred_y"],
        )
        tool_search_tool = _make_tool("tool_search")

        # Turn 0: empty discovery
        discovery_0 = DiscoveryState()
        result_0 = ToolsAssembler.build_tools(catalog, discovery_0, tool_search_tool)

        # Turn 1: 2 discovered tools
        discovery_1 = DiscoveryState()
        discovery_1.add("deferred_x")
        discovery_1.add("deferred_y")
        result_1 = ToolsAssembler.build_tools(catalog, discovery_1, tool_search_tool)

        prefix_len = len(catalog.core_tools) + 1  # +1 for tool_search
        assert len(result_0.tools) == prefix_len  # core + tool_search only
        assert len(result_1.tools) == prefix_len + 2  # + 2 discovered

        # Prefix elements are the same object references
        for i in range(prefix_len):
            assert result_0.tools[i] is result_1.tools[i], (
                f"Prefix tool at index {i} is not the same object reference"
            )

    def test_prefix_length(self):
        """Prefix length == len(core_tools) + (1 if tool_search_tool else 0)."""
        catalog = _build_catalog(
            core_names=["core_a", "core_b"],
            deferred_names=["deferred_x"],
        )

        # With tool_search
        tool_search_tool = _make_tool("tool_search")
        result = ToolsAssembler.build_tools(catalog, DiscoveryState(), tool_search_tool)
        assert len(result.tools) == len(catalog.core_tools) + 1

        # Without tool_search
        result_no_search = ToolsAssembler.build_tools(catalog, DiscoveryState(), None)
        assert len(result_no_search.tools) == len(catalog.core_tools)


# ===========================================================================
# ASM-03: Monotonic growth
# ===========================================================================


class TestMonotonicGrowth:
    """ASM-03: ToolSet only grows across conversation turns."""

    def test_tools_only_grow(self):
        """ToolSet from turn N is a prefix of ToolSet from turn N+1."""
        catalog = _build_catalog(
            core_names=["core_a"],
            deferred_names=["deferred_x", "deferred_y"],
        )
        tool_search_tool = _make_tool("tool_search")

        # Turn 0: empty discovery
        discovery = DiscoveryState()
        result_0 = ToolsAssembler.build_tools(catalog, discovery, tool_search_tool)

        # Turn 1: discover deferred_x
        discovery.add("deferred_x")
        result_1 = ToolsAssembler.build_tools(catalog, discovery, tool_search_tool)

        # Turn 2: discover deferred_y
        discovery.add("deferred_y")
        result_2 = ToolsAssembler.build_tools(catalog, discovery, tool_search_tool)

        # Lengths monotonically increase
        assert len(result_0.tools) <= len(result_1.tools) <= len(result_2.tools)

        # Turn 0 tools are a prefix of turn 1 tools
        for i, tool in enumerate(result_0.tools):
            assert result_1.tools[i] is tool, (
                f"Turn 0 tool at index {i} is not a prefix of turn 1"
            )

        # Turn 1 tools are a prefix of turn 2 tools
        for i, tool in enumerate(result_1.tools):
            assert result_2.tools[i] is tool, (
                f"Turn 1 tool at index {i} is not a prefix of turn 2"
            )

    def test_returns_new_toolset_each_call(self):
        """build_tools() returns different ToolSet instances, not a shared one."""
        catalog = _build_catalog(
            core_names=["core_a"],
            deferred_names=[],
        )
        tool_search_tool = _make_tool("tool_search")
        discovery = DiscoveryState()

        result_a = ToolsAssembler.build_tools(catalog, discovery, tool_search_tool)
        result_b = ToolsAssembler.build_tools(catalog, discovery, tool_search_tool)

        assert result_a is not result_b
