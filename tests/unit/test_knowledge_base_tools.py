from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_retrieve_knowledge_base_reports_all_invalid_session_kbs(monkeypatch):
    from astrbot.core.tools import knowledge_base_tools

    context = MagicMock()
    context.kb_manager.get_kb = AsyncMock(return_value=None)

    monkeypatch.setattr(
        knowledge_base_tools.sp,
        "session_get",
        AsyncMock(return_value={"kb_ids": ["missing-kb"], "top_k": 5}),
    )

    result = await knowledge_base_tools.retrieve_knowledge_base(
        query="hello",
        umo="session-1",
        context=context,
    )

    assert result == "会话配置的知识库均不存在或未加载，请检查知识库设置。"
    context.kb_manager.retrieve.assert_not_called()
