from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

# Import astrbot.api first: the kb retrieval import chain
# (manager -> kb_helper -> provider.manager -> persona_mgr -> astrbot.api)
# only resolves when astrbot.api is fully initialized beforehand.
import astrbot.api  # noqa: F401
from astrbot.core.knowledge_base.retrieval.manager import RetrievalManager


def _make_manager() -> RetrievalManager:
    manager = RetrievalManager(
        sparse_retriever=MagicMock(),
        rank_fusion=MagicMock(),
        kb_db=MagicMock(),
    )
    manager.rank_fusion.fuse = AsyncMock(return_value=[])
    manager.kb_db.get_documents_with_metadata_batch = AsyncMock(return_value={})
    return manager


@pytest.mark.asyncio
async def test_invisible_only_query_skips_retrieval() -> None:
    manager = _make_manager()
    manager._dense_retrieve = AsyncMock(return_value=[])
    manager.sparse_retriever.retrieve = AsyncMock(return_value=[])

    results = await manager.retrieve(
        query="\u200b\ufeff\x00",
        kb_ids=["kb-1"],
        kb_id_helper_map={},
    )

    assert results == []
    manager._dense_retrieve.assert_not_awaited()
    manager.sparse_retriever.retrieve.assert_not_awaited()


@pytest.mark.asyncio
async def test_invisible_chars_are_stripped_before_retrieval() -> None:
    manager = _make_manager()
    manager._dense_retrieve = AsyncMock(return_value=[])
    manager.sparse_retriever.retrieve = AsyncMock(return_value=[])
    manager.rank_fusion.fuse = AsyncMock(return_value=[])

    kb_helper = MagicMock()
    kb_helper.kb.top_k_dense = 50
    kb_helper.kb.top_k_sparse = 50
    kb_helper.kb.top_m_final = 5
    kb_helper.vec_db.rerank_provider = None

    results = await manager.retrieve(
        query="\u200bOni\u200f 恶鬼 ",
        kb_ids=["kb-1"],
        kb_id_helper_map={"kb-1": kb_helper},
    )

    assert results == []
    sent_query = manager._dense_retrieve.await_args.kwargs["query"]
    assert sent_query == "Oni 恶鬼"
