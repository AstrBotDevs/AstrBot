"""Import smoke tests for the sparse retriever module."""

from __future__ import annotations

from astrbot.core.knowledge_base.retrieval.sparse_retriever import (
    SparseResult,
    SparseRetriever,
)


class TestSparseRetrieverImports:
    """Verify that the main classes from sparse_retriever can be imported."""

    def test_import_sparse_retriever(self):
        assert SparseRetriever is not None
        assert hasattr(SparseRetriever, "retrieve")

    def test_import_sparse_result(self):
        assert SparseResult is not None
        fields = SparseResult.__dataclass_fields__
        assert {"chunk_id", "doc_id", "content", "score"} <= fields.keys()
