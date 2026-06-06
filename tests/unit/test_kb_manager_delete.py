from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_delete_kb_removes_related_document_and_media_metadata(tmp_path):
    from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
    from astrbot.core.knowledge_base.models import (
        KBDocument,
        KBMedia,
        KnowledgeBase,
    )

    kb_db = KBSQLiteDatabase(str(tmp_path / "kb.db"))
    await kb_db.initialize()
    await kb_db.migrate_to_v1()

    kb = KnowledgeBase(
        kb_id="kb-delete",
        kb_name="delete-me",
        embedding_provider_id="emb-1",
    )
    other_kb = KnowledgeBase(
        kb_id="kb-keep",
        kb_name="keep-me",
        embedding_provider_id="emb-1",
    )
    doc = KBDocument(
        doc_id="doc-delete",
        kb_id="kb-delete",
        doc_name="delete.txt",
        file_type="txt",
        file_size=1,
        file_path="",
    )
    other_doc = KBDocument(
        doc_id="doc-keep",
        kb_id="kb-keep",
        doc_name="keep.txt",
        file_type="txt",
        file_size=1,
        file_path="",
    )
    media = KBMedia(
        media_id="media-delete",
        doc_id="doc-delete",
        kb_id="kb-delete",
        media_type="image",
        file_name="delete.png",
        file_path="",
        file_size=1,
        mime_type="image/png",
        created_at=datetime.now(timezone.utc),
    )
    other_media = KBMedia(
        media_id="media-keep",
        doc_id="doc-keep",
        kb_id="kb-keep",
        media_type="image",
        file_name="keep.png",
        file_path="",
        file_size=1,
        mime_type="image/png",
        created_at=datetime.now(timezone.utc),
    )
    async with kb_db.get_db() as session:
        session.add(kb)
        session.add(other_kb)
        session.add(doc)
        session.add(other_doc)
        session.add(media)
        session.add(other_media)
        await session.commit()

    helper = KBHelper.__new__(KBHelper)
    helper.kb = kb
    helper.delete_vec_db = AsyncMock()

    manager = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    manager.kb_db = kb_db
    manager.kb_insts = {"kb-delete": helper}

    deleted = await manager.delete_kb("kb-delete")

    assert deleted is True
    helper.delete_vec_db.assert_awaited_once()
    assert await kb_db.get_kb_by_id("kb-delete") is None
    assert await kb_db.get_document_by_id("doc-delete") is None
    assert await kb_db.get_media_by_id("media-delete") is None
    assert await kb_db.get_kb_by_id("kb-keep") is not None
    assert await kb_db.get_document_by_id("doc-keep") is not None
    assert await kb_db.get_media_by_id("media-keep") is not None
    assert await manager.get_kb_by_name("delete-me") is None

    await kb_db.close()


@pytest.mark.asyncio
async def test_create_kb_cleans_created_directory_when_initialize_fails(
    tmp_path,
    monkeypatch,
):
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    manager = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    manager.provider_manager = MagicMock()
    manager.kb_db = MagicMock()
    manager.kb_insts = {}

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    manager.kb_db.get_db.return_value = context

    async def fail_initialize(self):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(KBHelper, "initialize", fail_initialize)
    monkeypatch.setattr("astrbot.core.knowledge_base.kb_mgr.FILES_PATH", str(tmp_path))

    with pytest.raises(RuntimeError, match="provider unavailable"):
        await manager.create_kb(
            kb_name="broken",
            embedding_provider_id="emb-1",
        )

    assert list(tmp_path.iterdir()) == []
