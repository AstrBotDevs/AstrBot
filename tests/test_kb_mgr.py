"""Knowledge manager initializes isolated storage and preserves unavailable bases."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from astrbot.core.knowledge_base import kb_mgr
from astrbot.core.knowledge_base.models import KnowledgeBase


@pytest_asyncio.fixture
async def manager(monkeypatch, tmp_path):
    monkeypatch.setattr(kb_mgr, "DB_PATH", tmp_path / "kb.db")
    monkeypatch.setattr(kb_mgr, "FILES_PATH", str(tmp_path))
    instance = kb_mgr.KnowledgeBaseManager(SimpleNamespace())
    try:
        await instance.initialize()
        yield instance
    finally:
        await instance.terminate()


@pytest.mark.asyncio
async def test_initialization_creates_queryable_empty_storage(manager):
    assert await manager.list_kbs() == []
    assert await manager.get_kb("missing") is None
    assert await manager.get_kb_by_name("missing") is None
    assert await manager.retrieve("question", ["missing"]) == {}
    assert manager.kb_insts == {}


@pytest.mark.asyncio
async def test_unavailable_base_is_listed_and_reports_retrieval_failure(manager):
    record = KnowledgeBase(kb_name="unavailable")
    async with manager.kb_db.get_db() as session:
        session.add(record)
        await session.commit()
    await manager.load_kbs()

    helper = await manager.get_kb_by_name("unavailable")
    assert helper is not None
    assert helper.kb.kb_id == record.kb_id
    assert helper.init_error
    assert [item.kb_id for item in await manager.list_kbs()] == [record.kb_id]
    with pytest.raises(ValueError, match="unavailable"):
        await manager.retrieve("question", ["unavailable"])


@pytest.mark.asyncio
async def test_termination_continues_after_one_helper_fails(manager):
    broken = SimpleNamespace(
        terminate=AsyncMock(side_effect=RuntimeError("close failed"))
    )
    healthy = SimpleNamespace(terminate=AsyncMock())
    manager.kb_insts = {"broken": broken, "healthy": healthy}

    await manager.terminate()

    broken.terminate.assert_awaited_once()
    healthy.terminate.assert_awaited_once()
    assert manager.kb_insts == {}
