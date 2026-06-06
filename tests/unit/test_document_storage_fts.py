import asyncio
import sqlite3

import pytest
from sqlalchemy.exc import IntegrityError

from astrbot.core.db.vec_db.faiss_impl.document_storage import DocumentStorage


@pytest.mark.asyncio
async def test_document_storage_fts_insert_search_and_delete(tmp_path):
    storage = DocumentStorage(str(tmp_path / "doc.db"))
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

    await storage.close()


@pytest.mark.asyncio
async def test_document_storage_fts_rebuilds_existing_documents(tmp_path):
    storage = DocumentStorage(str(tmp_path / "doc.db"))
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

    await storage.close()


@pytest.mark.asyncio
async def test_document_storage_search_documents_filters_and_paginates(tmp_path):
    storage = DocumentStorage(str(tmp_path / "doc.db"))
    await storage.initialize()

    await storage.insert_documents_batch(
        doc_ids=["chunk-1", "chunk-2", "chunk-3"],
        texts=[
            "AstrBot plugin lifecycle",
            "AstrBot provider lifecycle",
            "unrelated content",
        ],
        metadatas=[
            {"kb_doc_id": "doc-1", "kb_id": "kb-1", "chunk_index": 0},
            {"kb_doc_id": "doc-1", "kb_id": "kb-1", "chunk_index": 1},
            {"kb_doc_id": "doc-2", "kb_id": "kb-1", "chunk_index": 0},
        ],
    )

    result = await storage.search_documents(
        "lifecycle",
        metadata_filters={"kb_doc_id": "doc-1"},
        offset=1,
        limit=1,
    )

    assert result is not None
    docs, total = result
    assert total == 2
    assert [doc["doc_id"] for doc in docs] == ["chunk-2"]

    await storage.close()


@pytest.mark.asyncio
async def test_document_storage_search_sparse_non_positive_limit_falls_back(tmp_path):
    storage = DocumentStorage(str(tmp_path / "doc.db"))
    await storage.initialize()

    assert await storage.search_sparse(["知识库"], limit=0) is None

    await storage.close()


@pytest.mark.asyncio
async def test_document_storage_fts_rebuild_is_serialized(tmp_path, monkeypatch):
    storage = DocumentStorage(str(tmp_path / "doc.db"))
    await storage.initialize()

    storage.fts5_available = False
    await storage.insert_document(
        doc_id="legacy-chunk",
        text="legacy 知识库 文本",
        metadata={"kb_doc_id": "doc-1", "kb_id": "kb-1", "chunk_index": 0},
    )

    storage.fts5_available = True
    storage._fts_index_ready = False
    rebuild_count = 0
    original_rebuild = storage._rebuild_fts_index_unlocked

    async def counted_rebuild():
        nonlocal rebuild_count
        rebuild_count += 1
        await asyncio.sleep(0)
        await original_rebuild()

    monkeypatch.setattr(storage, "_rebuild_fts_index_unlocked", counted_rebuild)

    results = await asyncio.gather(
        storage.ensure_fts_index(),
        storage.ensure_fts_index(),
        storage.ensure_fts_index(),
    )

    assert results == [True, True, True]
    assert rebuild_count == 1

    await storage.close()


@pytest.mark.asyncio
async def test_document_storage_fts_delete_skips_missing_fts_row(tmp_path):
    storage = DocumentStorage(str(tmp_path / "doc.db"))
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

    await storage.close()


@pytest.mark.asyncio
async def test_document_storage_fts_recovers_from_legacy_non_fts_table(tmp_path):
    db_path = tmp_path / "doc.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE documents_fts (rowid INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    storage = DocumentStorage(str(db_path))
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

    await storage.close()


@pytest.mark.asyncio
async def test_document_storage_adds_unique_doc_id_index_to_existing_table(tmp_path):
    db_path = tmp_path / "doc.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id VARCHAR NOT NULL,
            text VARCHAR NOT NULL,
            metadata TEXT,
            created_at DATETIME,
            updated_at DATETIME
        )
        """,
    )
    conn.execute(
        "INSERT INTO documents (doc_id, text) VALUES ('legacy-chunk', 'legacy text')"
    )
    conn.commit()
    conn.close()

    storage = DocumentStorage(str(db_path))
    await storage.initialize()

    with pytest.raises(IntegrityError):
        await storage.insert_document(
            doc_id="legacy-chunk",
            text="duplicate text",
            metadata={},
        )

    await storage.close()


@pytest.mark.asyncio
async def test_document_storage_adds_missing_kb_id_generated_column(tmp_path):
    db_path = tmp_path / "doc.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id VARCHAR NOT NULL,
            text VARCHAR NOT NULL,
            metadata TEXT,
            created_at DATETIME,
            updated_at DATETIME,
            kb_doc_id TEXT GENERATED ALWAYS AS
                (json_extract(metadata, '$.kb_doc_id')) VIRTUAL
        )
        """,
    )
    conn.execute(
        """
        INSERT INTO documents (doc_id, text, metadata)
        VALUES (
            'legacy-chunk',
            'legacy text',
            '{"kb_doc_id":"doc-1","kb_id":"kb-1","chunk_index":0}'
        )
        """,
    )
    conn.commit()
    conn.close()

    storage = DocumentStorage(str(db_path))
    await storage.initialize()

    docs = await storage.get_documents(metadata_filters={"kb_id": "kb-1"})

    assert [doc["doc_id"] for doc in docs] == ["legacy-chunk"]

    await storage.close()
