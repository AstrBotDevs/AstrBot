"""Import smoke tests for the recursive character chunker module."""

from __future__ import annotations

from astrbot.core.knowledge_base.chunking.recursive import (
    RecursiveCharacterChunker,
)


class TestRecursiveChunkerImports:
    """Verify that the main class from recursive can be imported."""

    def test_import_recursive_character_chunker(self):
        assert RecursiveCharacterChunker is not None
        assert hasattr(RecursiveCharacterChunker, "chunk")
        assert hasattr(RecursiveCharacterChunker, "_split_by_character")
