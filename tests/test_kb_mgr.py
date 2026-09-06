"""Import smoke tests for the knowledge base manager module."""

from __future__ import annotations

from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager


class TestKnowledgeBaseManagerImports:
    """Verify that the main class from kb_mgr can be imported."""

    def test_import_knowledge_base_manager(self):
        assert KnowledgeBaseManager is not None
        assert hasattr(KnowledgeBaseManager, "initialize")
        assert hasattr(KnowledgeBaseManager, "create_kb")
        assert hasattr(KnowledgeBaseManager, "delete_kb")
        assert hasattr(KnowledgeBaseManager, "retrieve")
        assert hasattr(KnowledgeBaseManager, "terminate")
