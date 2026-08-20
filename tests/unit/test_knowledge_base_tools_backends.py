from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.api.knowledge_base import (
    KnowledgeBaseHit,
    KnowledgeBaseInfo,
    KnowledgeBaseRef,
    KnowledgeBaseResponse,
)
from astrbot.core.tools.knowledge_base_tools import retrieve_knowledge_base


@pytest.fixture
def context() -> MagicMock:
    context = MagicMock()
    context.get_config.return_value = {
        "kb_names": [],
        "kb_final_top_k": 5,
        "kb_fusion_top_k": 20,
    }
    context.kb_manager.backends = {"builtin": MagicMock()}
    context.kb_manager.list_registered_knowledge_bases = AsyncMock(return_value=[])
    context.kb_manager.retrieve_from_backends = AsyncMock(
        return_value=KnowledgeBaseResponse(hits=[])
    )
    return context


@pytest.mark.asyncio
async def test_external_backend_works_without_builtin_configuration(
    context: MagicMock,
) -> None:
    context.kb_manager.backends["dify:company"] = MagicMock()
    context.kb_manager.list_registered_knowledge_bases.return_value = [
        KnowledgeBaseInfo(
            ref=KnowledgeBaseRef("dify:company", "dataset-1"),
            name="Product Docs",
        )
    ]
    context.kb_manager.retrieve_from_backends.return_value = KnowledgeBaseResponse(
        hits=[
            KnowledgeBaseHit(
                content="Install AstrBot with uv.",
                source="guide.md",
                rank=1,
                score=0.93,
                source_uri="https://example.com/guide",
            )
        ]
    )

    with patch(
        "astrbot.core.tools.knowledge_base_tools.sp.session_get",
        AsyncMock(return_value={}),
    ):
        result = await retrieve_knowledge_base("installation", "session-1", context)

    assert "外部知识 1" in result
    assert "Install AstrBot with uv." in result
    assert "https://example.com/guide" in result
    refs, request = context.kb_manager.retrieve_from_backends.await_args.args
    assert refs == [KnowledgeBaseRef("dify:company", "dataset-1")]
    assert request.query == "installation"
    assert request.umo == "session-1"
    context.kb_manager.list_registered_knowledge_bases.assert_awaited_once_with(
        umo="session-1",
        backend_ids={"dify:company"},
    )


@pytest.mark.asyncio
async def test_builtin_retrieval_keeps_existing_configuration(
    context: MagicMock,
) -> None:
    context.get_config.return_value = {
        "kb_names": ["Docs"],
        "kb_final_top_k": 4,
        "kb_fusion_top_k": 9,
    }
    helper = MagicMock()
    helper.kb.doc_count = 1
    helper.kb.chunk_count = 2
    context.kb_manager.get_kb_by_name = AsyncMock(return_value=helper)
    context.kb_manager.retrieve = AsyncMock(
        return_value={
            "context_text": "built-in context",
            "results": [{"content": "built-in result"}],
        }
    )

    with patch(
        "astrbot.core.tools.knowledge_base_tools.sp.session_get",
        AsyncMock(return_value={}),
    ):
        result = await retrieve_knowledge_base("installation", "session-1", context)

    assert result == "built-in context"
    context.kb_manager.retrieve.assert_awaited_once_with(
        query="installation",
        kb_names=["Docs"],
        top_k_fusion=9,
        top_m_final=4,
    )


@pytest.mark.asyncio
async def test_builtin_and_external_results_are_combined(context: MagicMock) -> None:
    context.kb_manager.backends["external"] = MagicMock()
    context.get_config.return_value = {
        "kb_names": ["Docs"],
        "kb_final_top_k": 5,
        "kb_fusion_top_k": 20,
    }
    helper = MagicMock()
    helper.kb.doc_count = 1
    helper.kb.chunk_count = 2
    context.kb_manager.get_kb_by_name = AsyncMock(return_value=helper)
    context.kb_manager.retrieve = AsyncMock(
        return_value={"context_text": "built-in context", "results": [{}]}
    )
    context.kb_manager.list_registered_knowledge_bases.return_value = [
        KnowledgeBaseInfo(
            ref=KnowledgeBaseRef("external", "kb-1"),
            name="External",
        )
    ]
    context.kb_manager.retrieve_from_backends.return_value = KnowledgeBaseResponse(
        hits=[KnowledgeBaseHit(content="external context", source="API", rank=1)]
    )

    with patch(
        "astrbot.core.tools.knowledge_base_tools.sp.session_get",
        AsyncMock(return_value={}),
    ):
        result = await retrieve_knowledge_base("installation", "session-1", context)

    assert result.startswith("built-in context")
    assert "external context" in result


@pytest.mark.asyncio
async def test_explicitly_disabled_session_skips_all_backends(
    context: MagicMock,
) -> None:
    with patch(
        "astrbot.core.tools.knowledge_base_tools.sp.session_get",
        AsyncMock(return_value={"kb_ids": []}),
    ):
        result = await retrieve_knowledge_base("installation", "session-1", context)

    assert result is None
    context.kb_manager.list_registered_knowledge_bases.assert_not_awaited()
    context.kb_manager.retrieve_from_backends.assert_not_awaited()
