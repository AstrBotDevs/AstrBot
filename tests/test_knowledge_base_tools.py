"""Knowledge tools route queries through the active session configuration."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.core.astr_agent_runtime.tools import knowledge_base_tools as tools


@pytest.mark.parametrize(
    ("counts", "empty"),
    [
        ([], True),
        ([None], True),
        ([(0, 0)], True),
        ([(1, 0)], False),
        ([(0, 1)], False),
        ([None, (0, 0), (2, 3)], False),
    ],
)
def test_check_all_kb_uses_document_and_chunk_counts(counts, empty):
    bases = [
        None
        if count is None
        else SimpleNamespace(
            kb=SimpleNamespace(doc_count=count[0], chunk_count=count[1])
        )
        for count in counts
    ]
    assert tools.check_all_kb(bases) is empty


@pytest.fixture
def context():
    manager = SimpleNamespace(
        get_kb_by_name=AsyncMock(
            return_value=SimpleNamespace(kb=SimpleNamespace(doc_count=1, chunk_count=2))
        ),
        retrieve=AsyncMock(
            return_value={"context_text": "indexed answer", "results": []}
        ),
    )
    return SimpleNamespace(
        kb_manager=manager,
        get_config=Mock(
            return_value={
                "kb_names": ["manual", "notes"],
                "kb_final_top_k": 3,
                "kb_fusion_top_k": 11,
            }
        ),
    )


@pytest.mark.asyncio
async def test_retrieve_uses_session_selection_and_limits(context):
    result = await tools.retrieve_knowledge_base("retry policy", "session-1", context)

    assert result == "indexed answer"
    context.get_config.assert_called_once_with(umo="session-1")
    assert [
        call.args[0] for call in context.kb_manager.get_kb_by_name.await_args_list
    ] == ["manual", "notes"]
    context.kb_manager.retrieve.assert_awaited_once_with(
        query="retry policy",
        kb_names=["manual", "notes"],
        top_k_fusion=11,
        top_m_final=3,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("names", [[], ["missing"]])
async def test_unconfigured_or_empty_bases_do_not_retrieve(context, names):
    context.get_config.return_value = {"kb_names": names}
    context.kb_manager.get_kb_by_name.return_value = None

    assert await tools.retrieve_knowledge_base("query", "session-1", context) is None
    context.kb_manager.retrieve.assert_not_awaited()
    if not names:
        context.kb_manager.get_kb_by_name.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [None, {}, {"context_text": ""}])
async def test_empty_retrieval_does_not_inject_context(context, result):
    context.kb_manager.retrieve.return_value = result
    assert await tools.retrieve_knowledge_base("query", "session-1", context) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "retrieved", "expected"),
    [
        ("", "unused", "error: Query parameter is empty."),
        ("query", None, "No relevant knowledge found."),
        ("query", "indexed answer", "indexed answer"),
    ],
)
async def test_query_tool_uses_runtime_context(
    monkeypatch, context, query, retrieved, expected
):
    retrieve = AsyncMock(return_value=retrieved)
    monkeypatch.setattr(tools, "retrieve_knowledge_base", retrieve)
    wrapper = SimpleNamespace(
        context=SimpleNamespace(
            event=SimpleNamespace(unified_msg_origin="session-1"),
            context=context,
        )
    )
    tool = tools.KnowledgeBaseQueryTool()

    assert await tool.call(wrapper, query=query) == expected
    assert tool.parameters["required"] == ["query"]
    if query:
        retrieve.assert_awaited_once_with(query=query, umo="session-1", context=context)
    else:
        retrieve.assert_not_awaited()
