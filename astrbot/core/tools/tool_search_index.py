"""Stateless BM25 search index for deferred tool discovery.

ToolSearchIndex is a frozen pydantic dataclass that builds a BM25 index
from tool metadata (name, description, parameter names, parameter
descriptions) at construction time. The search() method returns ranked
(FunctionTool, score) tuples filtered to score > 0 without mutating any
state.

This module reuses jieba tokenization and rank-bm25 (BM25Okapi) --
both already used by the knowledge base subsystem.
"""

from __future__ import annotations

import os

import jieba
from pydantic import Field, model_validator
from pydantic.dataclasses import dataclass
from rank_bm25 import BM25Okapi

from astrbot.core.agent.tool import FunctionTool

# ---------------------------------------------------------------------------
# Module-level stopwords (loaded once, not per-instance)
# ---------------------------------------------------------------------------

_STOPWORDS_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "knowledge_base",
    "retrieval",
    "hit_stopwords.txt",
)


def _load_stopwords() -> frozenset[str]:
    """Load stopwords from the shared hit_stopwords.txt file."""
    with open(_STOPWORDS_PATH, encoding="utf-8") as f:
        return frozenset(word.strip() for word in f.read().splitlines() if word.strip())


_STOPWORDS: frozenset[str] = _load_stopwords()

# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    """Tokenize text using jieba, filtering stopwords and single-char tokens.

    Reuses the same tokenization pattern as SparseRetriever.
    The ``len > 1`` filter is a known CJK limitation (single-char tokens
    are usually not meaningful Chinese words) kept as-is per CONTEXT.md;
    deferred to SQ-01 in v1.x.
    """
    return [w for w in jieba.cut(text) if len(w) > 1 and w not in _STOPWORDS]


# ---------------------------------------------------------------------------
# Search document construction
# ---------------------------------------------------------------------------


def _build_search_doc(tool: FunctionTool) -> str:
    """Build search text from tool metadata.

    Aligned with Claude's BM25 variant search surface:
    name + description + parameter names + parameter descriptions.
    """
    parts: list[str] = [tool.name, tool.description]
    props = tool.parameters.get("properties", {}) if tool.parameters else {}
    for param_name, param_schema in props.items():
        parts.append(param_name)
        desc = param_schema.get("description", "")
        if desc:
            parts.append(desc)
    return " ".join(parts)


# ---------------------------------------------------------------------------
# ToolSearchIndex
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolSearchIndex:
    """Immutable BM25 search index over deferred tools.

    Constructs a BM25 index from tool name, description, parameter names,
    and parameter descriptions at build time. The ``search()`` method returns
    ranked ``(FunctionTool, float)`` tuples filtered to ``score > 0``.

    Attributes:
        tools: The tuple of tools to index. Typically ``catalog.deferred_tools``.
    """

    tools: tuple[FunctionTool, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _build_index(self) -> ToolSearchIndex:
        """Build the BM25 index after construction."""
        # Build corpus from tool metadata
        corpus = [_build_search_doc(t) for t in self.tools]
        tokenized = [_tokenize(doc) for doc in corpus]

        # Guard: empty corpus or all-empty token lists cause ZeroDivisionError
        # in BM25Okapi (avgdl = 0).
        if tokenized and any(len(tokens) > 0 for tokens in tokenized):
            bm25 = BM25Okapi(tokenized)
        else:
            bm25 = None

        # Store computed state on frozen instance via object.__setattr__
        object.__setattr__(self, "_bm25", bm25)
        object.__setattr__(self, "_tools_list", list(self.tools))
        return self

    def search(
        self,
        query: str,
        max_results: int = 5,
    ) -> list[tuple[FunctionTool, float]]:
        """Search the index for tools matching *query*.

        Args:
            query: The search query string.
            max_results: Maximum number of results to return (default 5).

        Returns:
            A list of ``(FunctionTool, float)`` tuples sorted by descending
            score, filtered to ``score > 0``, limited to *max_results*.
        """
        if self._bm25 is None:  # type: ignore[has-type]
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)  # type: ignore[has-type]

        # Filter score > 0, pair with tools, sort descending
        # CRITICAL: Do NOT use get_top_n() -- it returns zero-score items
        results: list[tuple[FunctionTool, float]] = []
        for i, score in enumerate(scores):
            if score > 0:
                results.append((self._tools_list[i], float(score)))  # type: ignore[has-type]

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:max_results]
