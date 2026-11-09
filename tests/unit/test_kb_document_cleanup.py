"""
Unit tests for knowledge base document cleanup behavior.

Tests the following scenarios:
1. delete_document_by_id cleans up kb_media records
2. update_kb_stats counts chunks for the correct KB
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
from astrbot.core.knowledge_base.models import KBDocument, KBMedia, KnowledgeBase


@pytest_asyncio.fixture
async def kb_db(tmp_path):
    """Create a real KBSQLiteDatabase backed by a temporary file."""
    db_path = str(tmp_path / "test_kb.db")
    db = KBSQLiteDatabase(db_path)
    await db.initialize()
    await db.migrate_to_v1()
    return db


@pytest_asyncio.fixture
async def seeded_kb(kb_db):
    """Seed a knowledge base and return its kb_id."""
    kb = KnowledgeBase(
        kb_name="Test KB",
        description="A test knowledge base",
        embedding_provider_id="test-embedding",
    )
    async with kb_db.get_db() as session, session.begin():
        session.add(kb)
        await session.flush()
        kb_id = kb.kb_id
    return kb_id


@pytest_asyncio.fixture
async def seeded_doc(kb_db, seeded_kb):
    """Seed a document in the knowledge base and return (kb_id, doc_id)."""
    doc = KBDocument(
        kb_id=seeded_kb,
        doc_name="test_doc.txt",
        file_type="txt",
        file_size=100,
        file_path="",
    )
    async with kb_db.get_db() as session, session.begin():
        session.add(doc)
        await session.flush()
        doc_id = doc.doc_id
    return seeded_kb, doc_id


@pytest_asyncio.fixture
async def seeded_media(kb_db, seeded_doc):
    """Seed media records linked to the document."""
    kb_id, doc_id = seeded_doc

    media1 = KBMedia(
        doc_id=doc_id,
        kb_id=kb_id,
        media_type="image",
        file_name="img1.png",
        file_path="/tmp/fake/img1.png",
        file_size=1024,
        mime_type="image/png",
    )
    media2 = KBMedia(
        doc_id=doc_id,
        kb_id=kb_id,
        media_type="image",
        file_name="img2.png",
        file_path="/tmp/fake/img2.png",
        file_size=2048,
        mime_type="image/png",
    )
    async with kb_db.get_db() as session, session.begin():
        session.add(media1)
        session.add(media2)
        await session.flush()

    return kb_id, doc_id, (media1.media_id, media2.media_id)


@pytest.mark.asyncio
async def test_delete_document_cleans_media_records(kb_db, seeded_media):
    """删除文档时, kb_media 表中关联的多媒体记录应一并被删除。"""
    kb_id, doc_id, (media_id1, media_id2) = seeded_media

    # 验证 media 记录存在
    media_list = await kb_db.list_media_by_doc(doc_id)
    assert len(media_list) == 2

    # Mock vec_db
    mock_vec_db = MagicMock()
    mock_vec_db.delete_documents = AsyncMock()

    await kb_db.delete_document_by_id(doc_id, mock_vec_db)

    # 验证 media 记录已删除
    remaining = await kb_db.list_media_by_doc(doc_id)
    assert remaining == []

    # 验证 vec_db 也被调用
    mock_vec_db.delete_documents.assert_awaited_once_with(
        metadata_filters={"kb_doc_id": doc_id},
    )


@pytest.mark.asyncio
async def test_delete_document_keeps_other_doc_media(kb_db, seeded_kb):
    """删除一个文档时, 其他文档的多媒体记录不应受影响。"""
    kb_id = seeded_kb

    # 创建文档 A
    doc_a = KBDocument(
        kb_id=kb_id, doc_name="doc_a.txt", file_type="txt", file_size=100, file_path=""
    )
    # 创建文档 B
    doc_b = KBDocument(
        kb_id=kb_id, doc_name="doc_b.txt", file_type="txt", file_size=200, file_path=""
    )
    async with kb_db.get_db() as session, session.begin():
        session.add(doc_a)
        session.add(doc_b)
        await session.flush()
        doc_a_id = doc_a.doc_id
        doc_b_id = doc_b.doc_id

    # 为文档 B 创建 media
    media_b = KBMedia(
        doc_id=doc_b_id,
        kb_id=kb_id,
        media_type="image",
        file_name="b.png",
        file_path="/tmp/fake/b.png",
        file_size=512,
        mime_type="image/png",
    )
    async with kb_db.get_db() as session, session.begin():
        session.add(media_b)

    mock_vec_db = MagicMock()
    mock_vec_db.delete_documents = AsyncMock()

    await kb_db.delete_document_by_id(doc_a_id, mock_vec_db)

    # 文档 B 的 media 应仍在
    remaining_b = await kb_db.list_media_by_doc(doc_b_id)
    assert len(remaining_b) == 1
    assert remaining_b[0].file_name == "b.png"


@pytest.mark.asyncio
async def test_delete_document_removes_doc_record(kb_db, seeded_media):
    """删除文档时, KBDocument 记录应被删除。"""
    kb_id, doc_id, _ = seeded_media

    mock_vec_db = MagicMock()
    mock_vec_db.delete_documents = AsyncMock()

    await kb_db.delete_document_by_id(doc_id, mock_vec_db)

    doc = await kb_db.get_document_by_id(doc_id)
    assert doc is None


@pytest.mark.asyncio
async def test_update_kb_stats_counts_chunks_for_single_kb(kb_db, seeded_kb):
    """update_kb_stats 应只统计指定知识库的 chunk 数量。"""
    kb_id1 = seeded_kb

    # 创建第二个知识库
    kb2 = KnowledgeBase(
        kb_name="Second KB",
        description="Another test knowledge base",
        embedding_provider_id="test-embedding",
    )
    async with kb_db.get_db() as session, session.begin():
        session.add(kb2)
        await session.flush()
        kb_id2 = kb2.kb_id

    # Mock vec_db: count_documents 应被调用并带有 kb_id 过滤
    mock_vec_db = MagicMock()
    mock_vec_db.count_documents = AsyncMock(return_value=5)

    await kb_db.update_kb_stats(kb_id1, mock_vec_db)

    # 验证 count_documents 传入了正确的 metadata_filter
    mock_vec_db.count_documents.assert_awaited_once_with(
        metadata_filter={"kb_id": kb_id1},
    )
