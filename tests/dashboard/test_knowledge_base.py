"""Import smoke tests for the knowledge base route module.

Verifies that the ``KnowledgeBaseRoute`` class from ``knowledge_base.py``
can be imported without errors.
"""

from astrbot.dashboard.routes.knowledge_base import (
    KnowledgeBaseRoute,  # noqa: F401
)


def test_knowledge_base_route_class():
    assert KnowledgeBaseRoute is not None
