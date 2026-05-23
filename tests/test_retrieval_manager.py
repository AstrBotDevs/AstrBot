"""Import smoke tests for the retrieval manager module."""

from __future__ import annotations

from astrbot.core.knowledge_base.retrieval.manager import (
    RetrievalManager,
    RetrievalResult,
)


class TestRetrievalManagerImports:
    """Verify that the main classes from manager can be imported."""

    def test_import_retrieval_manager(self):
        assert RetrievalManager is not None
        assert hasattr(RetrievalManager, "retrieve")

    def test_import_retrieval_result(self):
        assert RetrievalResult is not None
        assert hasattr(RetrievalResult, "chunk_id")
        assert hasattr(RetrievalResult, "doc_id")
        assert hasattr(RetrievalResult, "content")
        assert hasattr(RetrievalResult, "score")
        assert hasattr(RetrievalResult, "metadata")
