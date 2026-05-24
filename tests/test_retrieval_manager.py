"""Import smoke tests for the retrieval manager module."""

from __future__ import annotations

from dataclasses import fields

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
        result_fields = {field.name for field in fields(RetrievalResult)}
        assert {
            "chunk_id",
            "doc_id",
            "content",
            "score",
            "metadata",
        }.issubset(result_fields)
