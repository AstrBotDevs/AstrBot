"""Tests for GenericToolSearchStrategy -- generic provider path (GEN-01, GEN-02, GEN-03, GEN-04)."""

import asyncio
import json

import pytest

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.tools.discovery_state import DiscoveryState
from astrbot.core.tools.tool_catalog import ToolCatalog
from astrbot.core.tools.tool_search_index import ToolSearchIndex
from astrbot.core.tools.tool_search_tool import ToolSearchTool

from astrbot.core.tools.strategy import ToolSearchStrategy
from astrbot.core.tools.generic_strategy import GenericToolSearchStrategy

# ---------------------------------------------------------------------------
# Helpers (self-contained, copied pattern from test_tools_assembler.py)
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "always_loaded_tools": [],
    "auto_always_load_builtin": True,
}


def _make_tool(
    name: str,
    *,
    description: str = "",
    handler_module_path: str | None = None,
    active: bool = True,
    params: dict | None = None,
) -> FunctionTool:
    """Create a minimal FunctionTool for testing."""
    if params is None:
        params = {"type": "object", "properties": {}}
    if not description:
        description = f"Description for {name}"
    return FunctionTool(
        name=name,
        description=description,
        parameters=params,
        handler_module_path=handler_module_path,
        active=active,
    )


def _build_catalog(
    core_names: list[str],
    deferred_names: list[str],
) -> ToolCatalog:
    """Build a ToolCatalog with specific core and deferred tools.

    Core tools: builtin (no handler_module_path) with auto_always_load_builtin=True.
    Deferred tools: plugin tools (with handler_module_path set) and rich descriptions.
    """
    tools = []
    for name in core_names:
        tools.append(_make_tool(name))  # builtin -> core
    for name in deferred_names:
        tools.append(
            _make_tool(
                name,
                description=f"Deferred tool that provides {name} functionality",
                handler_module_path=f"plugins.{name}",
                params={
                    "type": "object",
                    "properties": {
                        "input": {
                            "type": "string",
                            "description": f"Input for {name}",
                        },
                    },
                },
            )
        )  # plugin -> deferred
    ts = ToolSet(tools=tools)
    return ToolCatalog.from_tool_set(ts, DEFAULT_CONFIG)


def _build_strategy(
    core_names: list[str] | None = None,
    deferred_names: list[str] | None = None,
) -> GenericToolSearchStrategy:
    """Build a GenericToolSearchStrategy with catalog and index."""
    if core_names is None:
        core_names = ["core_a", "core_b"]
    if deferred_names is None:
        deferred_names = ["deferred_x", "deferred_y", "deferred_z"]
    catalog = _build_catalog(core_names, deferred_names)
    index = ToolSearchIndex(tools=catalog.deferred_tools)
    return GenericToolSearchStrategy(catalog=catalog, index=index)


# ===========================================================================
# GEN-01: build_tool_set returns filtered tools
# ===========================================================================


class TestBuildToolSet:
    """GEN-01: build_tool_set() returns ToolSet with core + tool_search, not undiscovered deferred."""

    def test_returns_toolset_instance(self):
        """build_tool_set() returns a ToolSet."""
        strategy = _build_strategy()
        result = strategy.build_tool_set()
        assert isinstance(result, ToolSet)

    def test_initial_contains_core_and_tool_search(self):
        """Initial build_tool_set() contains core tools and 'tool_search' only."""
        strategy = _build_strategy(
            core_names=["core_a", "core_b"],
            deferred_names=["deferred_x", "deferred_y", "deferred_z"],
        )
        result = strategy.build_tool_set()
        names = result.names()

        assert "core_a" in names
        assert "core_b" in names
        assert "tool_search" in names
        # Deferred tools should NOT be present initially
        assert "deferred_x" not in names
        assert "deferred_y" not in names
        assert "deferred_z" not in names

    def test_discovered_tool_appears_after_manual_add(self):
        """After manually adding to discovery_state, next build_tool_set includes the tool."""
        strategy = _build_strategy(
            core_names=["core_a", "core_b"],
            deferred_names=["deferred_x", "deferred_y", "deferred_z"],
        )
        # Manually add a tool to discovery state
        strategy._discovery_state.add("deferred_x")

        result = strategy.build_tool_set()
        names = result.names()

        assert "core_a" in names
        assert "core_b" in names
        assert "tool_search" in names
        assert "deferred_x" in names
        # Other deferred tools still not present
        assert "deferred_y" not in names
        assert "deferred_z" not in names

    def test_abc_subclass(self):
        """GenericToolSearchStrategy is a subclass of ToolSearchStrategy."""
        assert issubclass(GenericToolSearchStrategy, ToolSearchStrategy)


# ===========================================================================
# GEN-02: tool_search returns structured JSON
# ===========================================================================


class TestToolSearchResult:
    """GEN-02: get_tool_search_tool() returns ToolSearchTool with structured JSON output."""

    def test_get_tool_search_tool_returns_tool_search_tool(self):
        """get_tool_search_tool() returns a ToolSearchTool instance."""
        strategy = _build_strategy()
        tool = strategy.get_tool_search_tool()
        assert isinstance(tool, ToolSearchTool)

    def test_tool_search_returns_valid_json(self):
        """Calling tool_search returns valid JSON with required keys."""
        strategy = _build_strategy()
        tool = strategy.get_tool_search_tool()
        raw = asyncio.get_event_loop().run_until_complete(
            tool.call(None, query="deferred functionality")
        )
        parsed = json.loads(raw)

        assert "query" in parsed
        assert "matches" in parsed
        assert "total_found" in parsed

    def test_matches_have_required_keys(self):
        """Each match has 'name', 'description', 'score' keys."""
        strategy = _build_strategy()
        tool = strategy.get_tool_search_tool()
        raw = asyncio.get_event_loop().run_until_complete(
            tool.call(None, query="deferred functionality")
        )
        parsed = json.loads(raw)

        # Should have at least one match
        assert len(parsed["matches"]) > 0
        for match in parsed["matches"]:
            assert "name" in match
            assert "description" in match
            assert "score" in match
            assert isinstance(match["name"], str)
            assert isinstance(match["description"], str)
            assert isinstance(match["score"], (int, float))


# ===========================================================================
# GEN-03: Discovered tools appear on NEXT turn only
# ===========================================================================


class TestMultiTurnDiscovery:
    """GEN-03: Discovered tools appear in build_tool_set() only after a tool_search call (next turn)."""

    def test_multi_turn_flow(self):
        """End-to-end: build -> search -> build. Discovered tool appears only in second build."""
        strategy = _build_strategy(
            core_names=["core_a"],
            deferred_names=["deferred_x", "deferred_y", "deferred_z"],
        )

        # Turn 1: Initial build -- only core + tool_search
        turn1_tools = strategy.build_tool_set()
        turn1_names = turn1_tools.names()
        assert "core_a" in turn1_names
        assert "tool_search" in turn1_names
        assert "deferred_x" not in turn1_names

        # Simulate tool_search call during turn 1
        tool = strategy.get_tool_search_tool()
        raw = asyncio.get_event_loop().run_until_complete(
            tool.call(None, query="deferred functionality")
        )
        parsed = json.loads(raw)
        assert len(parsed["matches"]) > 0

        # IMPORTANT: turn1_tools should NOT contain discovered tools
        # (the turn1 ToolSet was already built before search)
        turn1_names_after_search = turn1_tools.names()
        assert "deferred_x" not in turn1_names_after_search

        # Turn 2: Second build -- should now include discovered tools
        turn2_tools = strategy.build_tool_set()
        turn2_names = turn2_tools.names()
        assert "core_a" in turn2_names
        assert "tool_search" in turn2_names
        # At least one deferred tool should now appear
        discovered_in_turn2 = [n for n in turn2_names if n.startswith("deferred_")]
        assert len(discovered_in_turn2) > 0

    def test_same_turn_toolset_unchanged(self):
        """The ToolSet from step 1 does NOT retroactively contain discovered tools."""
        strategy = _build_strategy(
            core_names=["core_a"],
            deferred_names=["deferred_x"],
        )

        # Build the ToolSet
        initial_tools = strategy.build_tool_set()
        initial_count = len(initial_tools.tools)

        # Search (causes discovery)
        tool = strategy.get_tool_search_tool()
        asyncio.get_event_loop().run_until_complete(
            tool.call(None, query="deferred functionality")
        )

        # The initial ToolSet object remains unchanged
        assert len(initial_tools.tools) == initial_count


# ===========================================================================
# GEN-04: No provider-specific fields
# ===========================================================================


class TestNoProviderSpecificFields:
    """GEN-04: No defer_loading, tool_reference, or provider-specific attributes."""

    def test_no_defer_loading_on_tools(self):
        """No tool in build_tool_set() output has a truthy 'defer_loading' attribute."""
        strategy = _build_strategy()
        result = strategy.build_tool_set()

        for tool in result.tools:
            if hasattr(tool, "defer_loading"):
                assert not tool.defer_loading, (
                    f"Tool {tool.name} has truthy defer_loading"
                )

    def test_tool_search_result_no_tool_reference(self):
        """tool_search JSON result does not contain 'tool_reference'."""
        strategy = _build_strategy()
        tool = strategy.get_tool_search_tool()
        raw = asyncio.get_event_loop().run_until_complete(
            tool.call(None, query="deferred functionality")
        )

        assert "tool_reference" not in raw

    def test_strategy_has_no_provider_specific_attrs(self):
        """GenericToolSearchStrategy has no defer_loading or tool_reference attributes."""
        strategy = _build_strategy()
        assert not hasattr(strategy, "defer_loading")
        assert not hasattr(strategy, "tool_reference")

    def test_strategy_has_no_provider_specific_methods(self):
        """GenericToolSearchStrategy class has no defer_loading or tool_reference methods."""
        assert not hasattr(GenericToolSearchStrategy, "defer_loading")
        assert not hasattr(GenericToolSearchStrategy, "tool_reference")
