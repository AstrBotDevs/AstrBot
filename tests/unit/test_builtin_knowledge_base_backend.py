from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.api.knowledge_base import KnowledgeBaseQuery, KnowledgeBaseRef
from astrbot.core.knowledge_base.builtin_backend import BuiltinKnowledgeBaseBackend
from astrbot.core.knowledge_base.models import KnowledgeBase


@pytest.mark.asyncio
async def test_builtin_backend_lists_existing_knowledge_bases() -> None:
    manager = MagicMock()
    manager.list_kbs = AsyncMock(
        return_value=[
            KnowledgeBase(
                kb_id="kb-1",
                kb_name="Docs",
                description="Product documentation",
                emoji="📘",
                doc_count=2,
                chunk_count=8,
            )
        ]
    )
    backend = BuiltinKnowledgeBaseBackend(manager)

    result = await backend.list_knowledge_bases(umo="session-1")

    assert result[0].ref == KnowledgeBaseRef("builtin", "kb-1")
    assert result[0].name == "Docs"
    assert result[0].metadata == {
        "emoji": "📘",
        "doc_count": 2,
        "chunk_count": 8,
    }


@pytest.mark.asyncio
async def test_builtin_backend_normalizes_retrieval_results() -> None:
    manager = MagicMock()
    helper = MagicMock()
    helper.kb.kb_name = "Docs"
    manager.get_kb = AsyncMock(return_value=helper)
    manager.retrieve = AsyncMock(
        return_value={
            "results": [
                {
                    "chunk_id": "chunk-1",
                    "doc_id": "doc-1",
                    "kb_id": "kb-1",
                    "kb_name": "Docs",
                    "doc_name": "guide.md",
                    "chunk_index": 2,
                    "content": "Install AstrBot with uv.",
                    "score": 0.91,
                    "char_count": 23,
                }
            ]
        }
    )
    backend = BuiltinKnowledgeBaseBackend(manager)

    response = await backend.retrieve(
        ["kb-1"],
        KnowledgeBaseQuery(query="installation", top_k=3),
    )

    manager.retrieve.assert_awaited_once_with(
        query="installation",
        kb_names=["Docs"],
        top_m_final=3,
    )
    assert response.hits[0].source == "guide.md"
    assert response.hits[0].ref == KnowledgeBaseRef("builtin", "kb-1")
    assert response.hits[0].document_id == "doc-1"
    assert response.hits[0].chunk_id == "chunk-1"
    assert response.hits[0].metadata["backend_id"] == "builtin"


@pytest.mark.asyncio
async def test_builtin_backend_reports_unknown_knowledge_base() -> None:
    manager = MagicMock()
    manager.get_kb = AsyncMock(return_value=None)
    backend = BuiltinKnowledgeBaseBackend(manager)

    response = await backend.retrieve(
        ["missing"],
        KnowledgeBaseQuery(query="installation"),
    )

    assert response.hits == []
    assert "was not found" in response.warnings[0]
    manager.retrieve.assert_not_called()
