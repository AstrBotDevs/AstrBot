"""Import smoke tests for the knowledge base models module."""

from __future__ import annotations

from astrbot.core.knowledge_base.models import (
    KBDocument,
    KBMedia,
    KnowledgeBase,
)


class TestKBModelsImports:
    """Verify that the main model classes from models can be imported."""

    def test_import_knowledge_base(self):
        assert KnowledgeBase is not None
        assert hasattr(KnowledgeBase, "kb_id")
        assert hasattr(KnowledgeBase, "kb_name")
        assert hasattr(KnowledgeBase, "embedding_provider_id")

    def test_import_kb_document(self):
        assert KBDocument is not None
        assert hasattr(KBDocument, "doc_id")
        assert hasattr(KBDocument, "kb_id")
        assert hasattr(KBDocument, "doc_name")

    def test_import_kb_media(self):
        assert KBMedia is not None
        assert hasattr(KBMedia, "media_id")
        assert hasattr(KBMedia, "doc_id")
        assert hasattr(KBMedia, "media_type")
