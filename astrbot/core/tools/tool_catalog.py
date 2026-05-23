"""Immutable tool catalog that partitions tools into core and deferred sets.

ToolCatalog is a frozen pydantic dataclass constructed from a ToolSet and
configuration dict. Once built, it cannot be mutated -- this guarantees
stable tool ordering for prefix-cache-friendly prompt construction.
"""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic.dataclasses import dataclass

from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.mcp_client import MCPTool
from astrbot.core.agent.tool import FunctionTool, ToolSet


def _is_core(
    tool: FunctionTool,
    *,
    always_loaded_names: frozenset[str],
    auto_always_load_builtin: bool,
) -> bool:
    """Determine whether *tool* should be classified as core (always loaded).

    Classification rules (evaluated in order, first match wins):
    1. Tool name is in the ``always_loaded_tools`` config list.
    2. Tool is a :class:`HandoffTool` (agent delegation must always be available).
    3. ``auto_always_load_builtin`` is enabled **and** the tool has no explicit
       ``handler_module_path`` (i.e. it is a built-in) **and** it is not an
       :class:`MCPTool` (MCP tools are always deferred).
    """
    if tool.name in always_loaded_names:
        return True
    if isinstance(tool, HandoffTool):
        return True
    if (
        auto_always_load_builtin
        and tool.handler_module_path is None
        and not isinstance(tool, MCPTool)
    ):
        return True
    return False


@dataclass(frozen=True)
class ToolCatalog:
    """Immutable, partitioned snapshot of available tools.

    Attributes:
        core_tools: Tools that are always sent to the LLM (handoffs, builtins,
            pinned tools).
        deferred_tools: Tools that are only loaded on demand via tool search.
    """

    core_tools: tuple[FunctionTool, ...] = Field(default_factory=tuple)
    deferred_tools: tuple[FunctionTool, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _build_index(self) -> ToolCatalog:
        """Build a name-based lookup index after construction."""
        by_name: dict[str, FunctionTool] = {}
        for tool in self.core_tools:
            by_name[tool.name] = tool
        for tool in self.deferred_tools:
            by_name[tool.name] = tool
        object.__setattr__(self, "_by_name", by_name)
        return self

    # -- Factory ----------------------------------------------------------

    @classmethod
    def from_tool_set(cls, tool_set: ToolSet, config: dict) -> ToolCatalog:
        """Create a :class:`ToolCatalog` from a :class:`ToolSet` and config.

        Args:
            tool_set: The mutable tool set to snapshot.
            config: The ``tool_search`` config dict containing
                ``always_loaded_tools`` and ``auto_always_load_builtin``.

        Returns:
            A new frozen :class:`ToolCatalog` instance.
        """
        always_loaded_names = frozenset(config.get("always_loaded_tools", []))
        auto_always_load_builtin = config.get("auto_always_load_builtin", True)

        core: list[FunctionTool] = []
        deferred: list[FunctionTool] = []

        for tool in sorted(tool_set.tools, key=lambda t: t.name):
            if not tool.active:
                continue
            if _is_core(
                tool,
                always_loaded_names=always_loaded_names,
                auto_always_load_builtin=auto_always_load_builtin,
            ):
                core.append(tool)
            else:
                deferred.append(tool)

        return cls(core_tools=tuple(core), deferred_tools=tuple(deferred))

    # -- Accessors --------------------------------------------------------

    def get_tool(self, name: str) -> FunctionTool | None:
        """Look up a tool by name across both partitions."""
        return self._by_name.get(name)  # type: ignore[attr-defined]

    @property
    def all_tools(self) -> tuple[FunctionTool, ...]:
        """Return all tools (core first, then deferred)."""
        return self.core_tools + self.deferred_tools

    def __len__(self) -> int:
        return len(self.core_tools) + len(self.deferred_tools)
