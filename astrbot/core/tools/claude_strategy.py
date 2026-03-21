"""Claude-native tool search strategy.

ClaudeToolSearchStrategy sends the FULL tool catalog on every request with
``defer_loading: true`` on deferred tools, and converts ToolSearchTool's JSON
output into ``tool_reference`` content blocks. The tools parameter is identical
on every request within a session for maximum prompt cache hit potential.

Phase 8 (Mode Management) will instantiate this strategy when the provider is
detected as Claude API. All search, discovery, and catalog logic is reused
from Phases 2-5; this phase adds Claude-specific serialization and formatting.
"""

from __future__ import annotations

import json

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.tools.discovery_state import DiscoveryState
from astrbot.core.tools.strategy import ToolSearchStrategy
from astrbot.core.tools.tool_catalog import ToolCatalog
from astrbot.core.tools.tool_search_index import ToolSearchIndex
from astrbot.core.tools.tool_search_tool import ToolSearchTool


def _tool_to_anthropic_dict(
    tool: FunctionTool,
    *,
    defer_loading: bool = False,
) -> dict:
    """Convert a single FunctionTool to an Anthropic API tool dict.

    Mirrors ``ToolSet.anthropic_schema()`` logic for a single tool, with
    optional ``defer_loading`` support for Claude-native tool search.

    Args:
        tool: The tool to serialize.
        defer_loading: If True, add ``"defer_loading": True`` to the dict.

    Returns:
        A dict suitable for the Anthropic ``tools`` parameter.
    """
    input_schema: dict = {"type": "object"}
    if tool.parameters:
        input_schema["properties"] = tool.parameters.get("properties", {})
        input_schema["required"] = tool.parameters.get("required", [])
    tool_def: dict = {"name": tool.name, "input_schema": input_schema}
    if tool.description:
        tool_def["description"] = tool.description
    if defer_loading:
        tool_def["defer_loading"] = True
    return tool_def


class ClaudeToolSearchStrategy(ToolSearchStrategy):
    """Claude-native tool search strategy.

    Sends the full tool catalog on every request with ``defer_loading: true``
    on deferred tools. Converts ToolSearchTool JSON output into
    ``tool_reference`` content blocks.

    The tools parameter (``build_tool_dicts()``) is pre-computed once at
    construction time and returned as the same object on every call,
    guaranteeing prompt cache stability.

    Args:
        catalog: The frozen tool catalog partitioning core vs. deferred tools.
        index: The BM25 search index over deferred tools.
        max_results: Maximum number of tool search results (default 5).
    """

    def __init__(
        self,
        catalog: ToolCatalog,
        index: ToolSearchIndex,
        max_results: int = 5,
        discovery_state: DiscoveryState | None = None,
    ) -> None:
        self._catalog = catalog
        self._discovery_state = discovery_state or DiscoveryState()
        self._tool_search_tool = ToolSearchTool(
            _index=index,
            _discovery_state=self._discovery_state,
            _max_results=max_results,
        )
        self._deferred_names = frozenset(t.name for t in catalog.deferred_tools)
        self._tool_dicts: list[dict] = self._build_all_tool_dicts()

    def _build_all_tool_dicts(self) -> list[dict]:
        """Pre-compute the full list of Anthropic tool dicts.

        Ordering: core tools first, then tool_search, then deferred tools.
        Only deferred tools get ``defer_loading: true``.

        Returns:
            A list of Anthropic API tool dicts.
        """
        dicts: list[dict] = []
        # Core tools (no defer_loading)
        for tool in self._catalog.core_tools:
            dicts.append(_tool_to_anthropic_dict(tool))
        # tool_search tool (no defer_loading -- must be visible without search)
        dicts.append(_tool_to_anthropic_dict(self._tool_search_tool))
        # Deferred tools (with defer_loading)
        for tool in self._catalog.deferred_tools:
            dicts.append(_tool_to_anthropic_dict(tool, defer_loading=True))
        return dicts

    def build_tool_dicts(self) -> list[dict]:
        """Return the pre-computed tools parameter for Anthropic API requests.

        Returns the same list object on every call -- the tools parameter
        never changes within a session, maximizing prompt cache hit rate.

        Returns:
            A list of Anthropic API tool dicts (same object every call).
        """
        return self._tool_dicts

    def build_tool_set(self) -> ToolSet:
        """Build a ToolSet with Anthropic-specific schema/formatting overrides.

        The returned ToolSet still contains all executable tools so the runner can
        resolve them locally, but it overrides Anthropic serialization to emit the
        precomputed deferred-loading tool dicts and exposes a formatter for
        tool_search results.

        Returns:
            A :class:`ToolSet` with the full tool catalog plus tool_search.
        """
        tools = list(self._catalog.all_tools) + [self._tool_search_tool]
        tool_set = ToolSet(tools=tools)
        tool_set._anthropic_schema_override = self._tool_dicts
        tool_set._anthropic_tool_search_formatter = self.format_tool_result
        return tool_set

    def get_tool_search_tool(self) -> ToolSearchTool:
        """Return the ToolSearchTool instance.

        Returns the same object every call (identity guaranteed).

        Returns:
            The :class:`ToolSearchTool` instance owned by this strategy.
        """
        return self._tool_search_tool

    def format_tool_result(self, tool_search_json: str) -> list[dict]:
        """Convert ToolSearchTool JSON output into tool_reference content blocks.

        Parses the JSON result from ToolSearchTool and produces a list of
        ``{"type": "tool_reference", "tool_name": name}`` dicts for each
        valid match that exists in the catalog's deferred tools.

        Args:
            tool_search_json: The JSON string returned by ToolSearchTool.call().

        Returns:
            A list of tool_reference content block dicts. Empty on error,
            invalid JSON, or no valid matches.
        """
        try:
            data = json.loads(tool_search_json)
        except (json.JSONDecodeError, TypeError):
            return []
        if "error" in data:
            return []
        return [
            {"type": "tool_reference", "tool_name": match["name"]}
            for match in data.get("matches", [])
            if "name" in match and match["name"] in self._deferred_names
        ]

    @staticmethod
    def is_server_tool_block(content_block_type: str) -> bool:
        """Check whether a content block type is a server-side tool block.

        Recognizes ``server_tool_use`` and ``tool_search_tool_result`` as
        server-side block types that should be handled differently from
        regular ``tool_use`` blocks.

        Args:
            content_block_type: The ``type`` field of a content block.

        Returns:
            True if the block type is a server-side tool block.
        """
        return content_block_type in ("server_tool_use", "tool_search_tool_result")
