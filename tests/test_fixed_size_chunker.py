"""Import smoke tests for the fixed size chunker module."""

from __future__ import annotations

from astrbot.core.knowledge_base.chunking.fixed_size import FixedSizeChunker


class TestFixedSizeChunkerImports:
    """Verify that the main class from fixed_size can be imported."""

    def test_import_fixed_size_chunker(self):
        assert FixedSizeChunker is not None
        assert hasattr(FixedSizeChunker, "chunk")
