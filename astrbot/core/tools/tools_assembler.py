"""Stateless assembler that builds a ToolSet for each LLM request."""

from __future__ import annotations

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.tools.discovery_state import DiscoveryState
from astrbot.core.tools.tool_catalog import ToolCatalog


class ToolsAssembler:
    """Assembles the tools parameter for each LLM request.

    This class is stateless -- :meth:`build_tools` is a pure function of
    its inputs. It produces a new :class:`ToolSet` every call with a
    deterministic ordering:

    1. **Core tools** from the catalog (frozen, sorted alphabetically).
    2. **tool_search tool** (constant across turns, omitted when ``None``).
    3. **Discovered tools** resolved from the catalog in discovery order.

    The prefix (core + tool_search) is identical across all turns in a
    session. Only the tail (discovered tools) grows monotonically.
    """

    @staticmethod
    def build_tools(
        catalog: ToolCatalog,
        discovery_state: DiscoveryState,
        tool_search_tool: FunctionTool | None = None,
    ) -> ToolSet:
        """Assemble tools parameter: core + tool_search + discovered (in order).

        Args:
            catalog: The immutable tool catalog.
            discovery_state: Session-level discovery tracker.
            tool_search_tool: The tool_search FunctionTool (Phase 5 creates
                this). Pass ``None`` to omit the tool_search slot.

        Returns:
            A new :class:`ToolSet` with deterministic ordering.
        """
        tools: list[FunctionTool] = []

        # 1. Core tools (frozen, sorted -- from ToolCatalog)
        tools.extend(catalog.core_tools)

        # 2. tool_search tool (constant across turns)
        if tool_search_tool is not None:
            tools.append(tool_search_tool)

        # 3. Discovered tools (in discovery order, from catalog lookup)
        for name in discovery_state.get_discovered_names():
            tool = catalog.get_tool(name)
            if tool is not None:
                tools.append(tool)
            # Names not found in catalog are silently skipped (graceful degradation)

        return ToolSet(tools=tools)
