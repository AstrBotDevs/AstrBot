"""Generic tool search strategy for non-native providers.

GenericToolSearchStrategy is the tool search path for all providers that do NOT
support native tool search features (OpenAI-compatible, DeepSeek, local models,
etc.). It physically filters the tools parameter via ToolsAssembler and passes
through ToolSearchTool's JSON results as standard function call results.

This class owns its session-scoped DiscoveryState and ToolSearchTool, and
delegates tool assembly to ToolsAssembler.build_tools().
"""

from __future__ import annotations

from astrbot.core.agent.tool import ToolSet
from astrbot.core.tools.discovery_state import DiscoveryState
from astrbot.core.tools.strategy import ToolSearchStrategy
from astrbot.core.tools.tool_catalog import ToolCatalog
from astrbot.core.tools.tool_search_index import ToolSearchIndex
from astrbot.core.tools.tool_search_tool import ToolSearchTool
from astrbot.core.tools.tools_assembler import ToolsAssembler


class GenericToolSearchStrategy(ToolSearchStrategy):
    """Concrete strategy for generic (non-native) providers.

    Assembles the tools parameter as: core + tool_search + discovered tools.
    ToolSearchTool's JSON result is returned as-is (already a JSON string
    from Phase 5). No provider-specific fields are used.

    Args:
        catalog: The immutable tool catalog (Phase 2).
        index: The BM25 search index over deferred tools (Phase 3).
        max_results: Maximum number of search results (default 5).
    """

    def __init__(
        self,
        catalog: ToolCatalog,
        index: ToolSearchIndex,
        max_results: int = 5,
    ) -> None:
        self._catalog = catalog
        self._discovery_state = DiscoveryState()
        self._tool_search_tool = ToolSearchTool(
            _index=index,
            _discovery_state=self._discovery_state,
            _max_results=max_results,
        )

    def build_tool_set(self) -> ToolSet:
        """Build tools parameter: core + tool_search + discovered (in order).

        Returns:
            A new :class:`ToolSet` with deterministic ordering via
            :meth:`ToolsAssembler.build_tools`.
        """
        return ToolsAssembler.build_tools(
            self._catalog,
            self._discovery_state,
            self._tool_search_tool,
        )

    def get_tool_search_tool(self) -> ToolSearchTool:
        """Return the session-scoped ToolSearchTool instance.

        Returns:
            The :class:`ToolSearchTool` owned by this strategy.
        """
        return self._tool_search_tool
