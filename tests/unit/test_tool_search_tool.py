"""Tests for ToolSearchTool -- LLM-callable tool search (TST-01, TST-02, TST-03, TST-04)."""

import asyncio
import json

import pytest

from astrbot.core.agent.tool import FunctionTool
from astrbot.core.tools.discovery_state import DiscoveryState
from astrbot.core.tools.tool_search_index import ToolSearchIndex
from astrbot.core.tools.tool_search_tool import ToolSearchTool

# Reuse shared corpus from index tests
from tests.unit.test_tool_search_index import ALL_TOOLS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_tool(
    discovery: DiscoveryState | None = None,
    index: ToolSearchIndex | None = None,
    max_results: int = 5,
) -> ToolSearchTool:
    """Build a ToolSearchTool with optional injected dependencies."""
    if index is None:
        index = ToolSearchIndex(tools=ALL_TOOLS)
    return ToolSearchTool(
        _index=index,
        _discovery_state=discovery,
        _max_results=max_results,
    )


# ===========================================================================
# TST-01: Registration
# ===========================================================================


class TestToolSearchToolBasics:
    """TST-01: ToolSearchTool is a FunctionTool subclass with correct schema."""

    def test_is_function_tool_subclass(self):
        """ToolSearchTool is an instance of FunctionTool."""
        tool = _build_tool()
        assert isinstance(tool, FunctionTool)

    def test_name_is_tool_search(self):
        """ToolSearchTool().name == 'tool_search'."""
        tool = _build_tool()
        assert tool.name == "tool_search"

    def test_has_query_parameter(self):
        """Parameters schema has a required 'query' property of type 'string'."""
        tool = _build_tool()
        assert "query" in tool.parameters["properties"]
        assert tool.parameters["properties"]["query"]["type"] == "string"
        assert "query" in tool.parameters["required"]

    def test_call_is_async(self):
        """tool.call() is a coroutine function."""
        tool = _build_tool()
        assert asyncio.iscoroutinefunction(tool.call)


# ===========================================================================
# TST-02: Structured Result
# ===========================================================================


class TestStructuredResult:
    """TST-02: call() returns valid JSON with query, matches, total_found."""

    @pytest.fixture()
    def tool_and_result(self):
        """Run a search and return (tool, parsed_result)."""
        discovery = DiscoveryState()
        tool = _build_tool(discovery=discovery)
        raw = asyncio.get_event_loop().run_until_complete(
            tool.call(None, query="weather forecast")
        )
        return tool, raw

    def test_returns_string(self, tool_and_result):
        """call() returns a str."""
        _tool, raw = tool_and_result
        assert isinstance(raw, str)

    def test_returns_valid_json(self, tool_and_result):
        """json.loads(result) succeeds."""
        _tool, raw = tool_and_result
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    def test_json_contains_required_fields(self, tool_and_result):
        """Parsed result has 'query', 'matches', 'total_found' keys."""
        _tool, raw = tool_and_result
        parsed = json.loads(raw)
        assert "query" in parsed
        assert "matches" in parsed
        assert "total_found" in parsed

    def test_matches_have_name_description_score(self, tool_and_result):
        """Each match dict has name (str), description (str), score (float)."""
        _tool, raw = tool_and_result
        parsed = json.loads(raw)
        assert len(parsed["matches"]) > 0, "Expected at least one match"
        for match in parsed["matches"]:
            assert isinstance(match["name"], str)
            assert isinstance(match["description"], str)
            assert isinstance(match["score"], (int, float))

    def test_scores_are_rounded(self, tool_and_result):
        """Each score has at most 2 decimal places."""
        _tool, raw = tool_and_result
        parsed = json.loads(raw)
        for match in parsed["matches"]:
            score_str = str(match["score"])
            if "." in score_str:
                decimals = len(score_str.split(".")[1])
                assert decimals <= 2, f"Score {match['score']} has more than 2 decimal places"

    def test_empty_query_returns_error(self):
        """Empty query returns JSON with 'error' key and empty matches."""
        tool = _build_tool(discovery=DiscoveryState())
        raw = asyncio.get_event_loop().run_until_complete(
            tool.call(None, query="")
        )
        parsed = json.loads(raw)
        assert "error" in parsed
        assert parsed["matches"] == []

    def test_no_index_returns_error(self):
        """When _index is None, returns JSON with 'error' key and empty matches."""
        tool = ToolSearchTool(_index=None, _discovery_state=DiscoveryState())
        raw = asyncio.get_event_loop().run_until_complete(
            tool.call(None, query="weather")
        )
        parsed = json.loads(raw)
        assert "error" in parsed
        assert parsed["matches"] == []


# ===========================================================================
# TST-03: Discovery Registration
# ===========================================================================


class TestDiscoveryRegistration:
    """TST-03: call() registers each matched tool name in DiscoveryState."""

    def test_matched_tools_registered(self):
        """After call(), each matched tool name appears in DiscoveryState."""
        discovery = DiscoveryState()
        tool = _build_tool(discovery=discovery)
        raw = asyncio.get_event_loop().run_until_complete(
            tool.call(None, query="weather forecast")
        )
        parsed = json.loads(raw)
        matched_names = [m["name"] for m in parsed["matches"]]

        assert len(matched_names) > 0
        for name in matched_names:
            assert name in discovery

    def test_no_duplicate_registration(self):
        """Calling tool_search twice with overlapping results does not create duplicates."""
        discovery = DiscoveryState()
        tool = _build_tool(discovery=discovery)

        # Call twice with the same query
        asyncio.get_event_loop().run_until_complete(
            tool.call(None, query="weather forecast")
        )
        asyncio.get_event_loop().run_until_complete(
            tool.call(None, query="weather forecast")
        )

        # Count unique names -- should equal the number of discovered names
        discovered = discovery.get_discovered_names()
        assert len(discovered) == len(set(discovered))

    def test_works_without_discovery_state(self):
        """call() succeeds when _discovery_state is None (no crash)."""
        tool = _build_tool(discovery=None)
        raw = asyncio.get_event_loop().run_until_complete(
            tool.call(None, query="weather forecast")
        )
        parsed = json.loads(raw)
        # Should still return results, just without registration
        assert "matches" in parsed
        assert len(parsed["matches"]) > 0


# ===========================================================================
# TST-04: No Mutation
# ===========================================================================


class TestNoMutation:
    """TST-04: call() does not mutate ToolSearchIndex or hold forbidden references."""

    def test_index_not_mutated(self):
        """id(index.tools) and id(index._bm25) are unchanged after call().

        Note: ids are captured AFTER ToolSearchTool construction because
        pydantic revalidates nested models during construction, which triggers
        ToolSearchIndex._build_index and rebuilds _bm25. The important
        invariant is that call() itself does not mutate the index.
        """
        index = ToolSearchIndex(tools=ALL_TOOLS)
        tool = ToolSearchTool(
            _index=index,
            _discovery_state=DiscoveryState(),
        )

        # Capture ids after construction (pydantic revalidation complete)
        tools_id_before = id(index.tools)
        bm25_id_before = id(index._bm25)

        asyncio.get_event_loop().run_until_complete(
            tool.call(None, query="weather forecast")
        )

        assert id(index.tools) == tools_id_before
        assert id(index._bm25) == bm25_id_before

    def test_no_toolset_reference(self):
        """ToolSearchTool has no tool_set, tool_catalog, or catalog attributes."""
        tool = _build_tool()
        assert not hasattr(tool, "tool_set")
        assert not hasattr(tool, "tool_catalog")
        assert not hasattr(tool, "catalog")

    def test_no_inject_into(self):
        """ToolSearchTool has no inject_into method."""
        tool = _build_tool()
        assert not hasattr(tool, "inject_into")
