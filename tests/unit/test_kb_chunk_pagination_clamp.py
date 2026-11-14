"""Regression tests for knowledge base chunk list pagination bounds."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.dashboard.services.knowledge_base_service import KnowledgeBaseService


def make_service(kb_helper: SimpleNamespace) -> KnowledgeBaseService:
    """Build a KnowledgeBaseService whose manager returns the given helper."""
    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    service.core_lifecycle = SimpleNamespace(kb_manager=kb_manager)
    return service


def make_kb_helper(calls: list[dict]) -> SimpleNamespace:
    """Build a kb helper stub that records the pagination it receives."""

    async def get_chunks_by_doc_id(*, doc_id: str, offset: int, limit: int) -> list:
        calls.append({"doc_id": doc_id, "offset": offset, "limit": limit})
        return []

    return SimpleNamespace(
        get_chunks_by_doc_id=get_chunks_by_doc_id,
        get_chunk_count_by_doc_id=AsyncMock(return_value=0),
    )


@pytest.mark.asyncio
async def test_list_chunks_clamps_zero_page_to_first_page():
    """page=0 must not forward a negative OFFSET to the document store."""
    calls: list[dict] = []
    service = make_service(make_kb_helper(calls))

    result = await service.list_chunks(
        kb_id="kb-1", doc_id="doc-1", page=0, page_size=20
    )

    assert calls == [{"doc_id": "doc-1", "offset": 0, "limit": 20}]
    assert result["page"] == 1
    assert result["page_size"] == 20


@pytest.mark.asyncio
async def test_list_chunks_clamps_non_positive_page_size():
    """A negative page_size becomes LIMIT -1, which SQLite reads as unlimited."""
    calls: list[dict] = []
    service = make_service(make_kb_helper(calls))

    result = await service.list_chunks(
        kb_id="kb-1", doc_id="doc-1", page=1, page_size=-1
    )

    assert calls == [{"doc_id": "doc-1", "offset": 0, "limit": 1}]
    assert result["page_size"] == 1
