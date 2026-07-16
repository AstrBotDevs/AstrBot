"""Import smoke tests for the knowledge base helper module."""

from __future__ import annotations

from astrbot.core.knowledge_base.kb_helper import KBHelper, RateLimiter


class TestKBHelperImports:
    """Verify that the main classes from kb_helper can be imported."""

    def test_import_kb_helper(self):
        assert KBHelper is not None
        assert hasattr(KBHelper, "initialize")
        assert hasattr(KBHelper, "upload_document")
        assert hasattr(KBHelper, "list_documents")
        assert hasattr(KBHelper, "delete_document")

    def test_import_rate_limiter(self):
        assert RateLimiter is not None
        assert hasattr(RateLimiter, "__aenter__")
        assert hasattr(RateLimiter, "__aexit__")
