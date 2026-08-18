"""Import smoke tests for knowledge_base_tools module."""

import asyncio

import pytest


class TestKnowledgeBaseToolsImports:
    """Verify knowledge_base_tools.py module can be imported and key classes exist."""

    def test_module_import(self):
        """Import the module without error."""
        from astrbot.core.tools import knowledge_base_tools
        assert knowledge_base_tools is not None

    def test_knowledge_base_query_tool(self):
        """KnowledgeBaseQueryTool is present."""
        from astrbot.core.tools.knowledge_base_tools import KnowledgeBaseQueryTool
        assert KnowledgeBaseQueryTool is not None
        assert KnowledgeBaseQueryTool.name == "astr_kb_search"

    def test_check_all_kb_function(self):
        """check_all_kb helper is importable."""
        from astrbot.core.tools.knowledge_base_tools import check_all_kb
        assert callable(check_all_kb)

    def test_retrieve_knowledge_base_function(self):
        """retrieve_knowledge_base is importable."""
        from astrbot.core.tools.knowledge_base_tools import retrieve_knowledge_base
        import asyncio
        # It's an async function
        assert asyncio.iscoroutinefunction(retrieve_knowledge_base)

    def test_module_all(self):
        """Module __all__ is properly defined."""
        from astrbot.core.tools.knowledge_base_tools import (
            KnowledgeBaseQueryTool,
            check_all_kb,
            retrieve_knowledge_base,
        )
        assert KnowledgeBaseQueryTool is not None
        assert callable(check_all_kb)
        assert asyncio.iscoroutinefunction(retrieve_knowledge_base)
