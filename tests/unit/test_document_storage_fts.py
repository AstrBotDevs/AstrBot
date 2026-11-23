import sqlite3

import pytest
import pytest_asyncio

from astrbot.core.db.vec_db.faiss_impl.document_storage import DocumentStorage


@pytest_asyncio.fixture
async def storage(tmp_path):
    instance = DocumentStorage(str(tmp_path / "doc.db"))
    try:
        yield instance
    finally:
        await instance.close()


@pytest.mark.asyncio
async def test_document_storage_fts_insert_search_and_delete(storage):
    await storage.initialize()

    assert storage.fts5_available is True

    await storage.insert_documents_batch(
        doc_ids=["chunk-1", "chunk-2"],
        texts=["AstrBot 知识库召回性能优化", "FAISS 向量检索"],
        metadatas=[
            {"kb_doc_id": "doc-1", "kb_id": "kb-1", "chunk_index": 0},
            {"kb_doc_id": "doc-1", "kb_id": "kb-1", "chunk_index": 1},
        ],
    )

    results = await storage.search_sparse(["知识库"], limit=10)

    assert results is not None
    assert [result["doc_id"] for result in results] == ["chunk-1"]

    await storage.delete_document_by_doc_id("chunk-1")
    results = await storage.search_sparse(["知识库"], limit=10)

    assert results == []


@pytest.mark.asyncio
async def test_document_storage_fts_rebuilds_existing_documents(storage):
    await storage.initialize()

    storage.fts5_available = False
    await storage.insert_document(
        doc_id="legacy-chunk",
        text="legacy 知识库 文本",
        metadata={"kb_doc_id": "doc-1", "kb_id": "kb-1", "chunk_index": 0},
    )

    storage.fts5_available = True
    storage._fts_index_ready = False

    results = await storage.search_sparse(["知识库"], limit=10)

    assert results is not None
    assert [result["doc_id"] for result in results] == ["legacy-chunk"]


@pytest.mark.asyncio
async def test_document_storage_fts_delete_skips_missing_fts_row(storage):
    await storage.initialize()

    storage.fts5_available = False
    await storage.insert_document(
        doc_id="legacy-chunk",
        text="legacy 知识库 文本",
        metadata={"kb_doc_id": "doc-1", "kb_id": "kb-1", "chunk_index": 0},
    )

    storage.fts5_available = True
    await storage.delete_document_by_doc_id("legacy-chunk")

    assert await storage.get_document_by_doc_id("legacy-chunk") is None


@pytest.mark.asyncio
async def test_document_storage_fts_recovers_from_legacy_non_fts_table(storage):
    db_path = storage.db_path
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE documents_fts (rowid INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    await storage.initialize()

    assert storage.fts5_available is True

    await storage.insert_document(
        doc_id="legacy-fix",
        text="legacy fts recovery text",
        metadata={"kb_doc_id": "doc-1", "kb_id": "kb-1", "chunk_index": 0},
    )
    results = await storage.search_sparse(["legacy"], limit=10)

    assert results is not None
    assert [result["doc_id"] for result in results] == ["legacy-fix"]
