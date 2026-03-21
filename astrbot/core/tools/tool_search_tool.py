"""LLM-callable tool for searching available tools by natural language query.

ToolSearchTool is a FunctionTool subclass that delegates to ToolSearchIndex
for BM25 search and registers discoveries in DiscoveryState. It returns a
JSON-serialized provider-agnostic result structure that Phase 6/7 will
reformat into provider-specific wire formats.

Result JSON schema:
    {
        "query": str,           # Echo of the input query
        "matches": [            # Ranked matches (may be empty)
            {
                "name": str,        # Tool name
                "description": str, # Tool description
                "score": float      # BM25 relevance score (rounded to 2 decimals)
            }
        ],
        "total_found": int      # Number of matches returned
    }

On error (empty query, no index):
    {
        "error": str,           # Human-readable error message
        "matches": []           # Always present, always empty on error
    }
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.tools.discovery_state import DiscoveryState
from astrbot.core.tools.tool_search_index import ToolSearchIndex


@dataclass
class ToolSearchTool(FunctionTool):
    """LLM-callable tool that searches for available tools by natural language query."""

    __pydantic_config__ = {"arbitrary_types_allowed": True}

    name: str = "tool_search"
    description: str = (
        "Search for available tools by describing what you need. "
        "Returns matching tool names and descriptions."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Natural language description of the tool capability you need."
                    ),
                },
            },
            "required": ["query"],
        }
    )

    # Injected dependencies (not frozen, normal field assignment)
    _index: ToolSearchIndex | None = Field(default=None, repr=False)
    _discovery_state: DiscoveryState | None = Field(default=None, repr=False)
    _max_results: int = Field(default=5, repr=False)

    async def call(self, context: Any = None, **kwargs) -> ToolExecResult:
        """Search for tools matching a natural language query.

        Args:
            context: Unused -- ToolSearchTool does not need agent context.
            **kwargs: Must contain ``query`` (str).

        Returns:
            A JSON string with query echo, ranked matches, and total count.
        """
        query = str(kwargs.get("query", "")).strip()
        if not query:
            return json.dumps({"error": "Query parameter is empty.", "matches": []})

        if self._index is None:
            return json.dumps({"error": "Search index not available.", "matches": []})

        results = self._index.search(query, max_results=self._max_results)

        matches = []
        for tool, score in results:
            if self._discovery_state is not None:
                self._discovery_state.add(tool.name)
            matches.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "score": round(score, 2),
                }
            )

        return json.dumps(
            {"query": query, "matches": matches, "total_found": len(matches)},
            ensure_ascii=False,
        )
