from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
from astrbot.core.tools import knowledge_base_tools


@pytest.mark.asyncio
async def test_get_kb_by_name_falls_back_to_kb_id():
    kb_manager = KnowledgeBaseManager(provider_manager=MagicMock())
    kb_helper = SimpleNamespace(
        kb=SimpleNamespace(kb_id="kb-uuid-1", kb_name="Docs"),
        init_error=None,
    )
    kb_manager.kb_insts = {"kb-uuid-1": kb_helper}

    with patch("astrbot.core.knowledge_base.kb_mgr.logger.warning") as warning:
        result = await kb_manager.get_kb_by_name("kb-uuid-1")

    assert result is kb_helper
    warning.assert_called_once()


@pytest.mark.asyncio
async def test_retrieve_knowledge_base_uses_resolved_names_for_global_uuid_config():
    kb_helper = SimpleNamespace(
        kb=SimpleNamespace(
            kb_id="kb-uuid-1",
            kb_name="Docs",
            doc_count=1,
            chunk_count=1,
        ),
        init_error=None,
    )
    kb_manager = MagicMock()
    kb_manager.get_kb_by_name = AsyncMock(return_value=kb_helper)
    kb_manager.retrieve = AsyncMock(
        return_value={"context_text": "knowledge context", "results": [object()]},
    )
    context = SimpleNamespace(
        kb_manager=kb_manager,
        get_config=lambda umo: {
            "kb_names": ["kb-uuid-1"],
            "kb_final_top_k": 3,
            "kb_fusion_top_k": 6,
        },
    )

    with patch.object(
        knowledge_base_tools.sp,
        "session_get",
        new=AsyncMock(return_value={}),
    ):
        result = await knowledge_base_tools.retrieve_knowledge_base(
            query="what is this",
            umo="umo:test",
            context=context,
        )

    assert result == "knowledge context"
    kb_manager.retrieve.assert_awaited_once_with(
        query="what is this",
        kb_names=["Docs"],
        top_k_fusion=6,
        top_m_final=3,
    )


@pytest.mark.asyncio
async def test_retrieve_knowledge_base_warns_for_invalid_global_kb_config():
    kb_manager = MagicMock()
    kb_manager.get_kb_by_name = AsyncMock(return_value=None)
    kb_manager.retrieve = AsyncMock()
    context = SimpleNamespace(
        kb_manager=kb_manager,
        get_config=lambda umo: {
            "kb_names": ["missing-kb"],
            "kb_final_top_k": 3,
            "kb_fusion_top_k": 6,
        },
    )

    with (
        patch.object(
            knowledge_base_tools.sp,
            "session_get",
            new=AsyncMock(return_value={}),
        ),
        patch.object(knowledge_base_tools.logger, "warning") as warning,
    ):
        result = await knowledge_base_tools.retrieve_knowledge_base(
            query="what is this",
            umo="umo:test",
            context=context,
        )

    assert result is None
    warning.assert_called_once_with(
        "[Knowledge Base] Session %s references missing or unloaded "
        "knowledge bases: %s",
        "umo:test",
        ["missing-kb"],
    )
    kb_manager.retrieve.assert_not_called()
