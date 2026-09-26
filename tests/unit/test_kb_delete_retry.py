"""Document deletion remains discoverable and retryable after storage failures."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from astrbot.core.db.vec_db.faiss_impl.vec_db import FaissVecDB
from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
from astrbot.core.knowledge_base.models import KBDocument, KBMedia, KnowledgeBase


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_stage", ["index_save", "chunk_delete", "metadata_delete"]
)
async def test_failed_document_delete_remains_listed_and_can_be_retried(
    tmp_path, monkeypatch, failure_stage
):
    kb_db = KBSQLiteDatabase(str(tmp_path / "kb.db"))
    provider = MagicMock()
    provider.get_dim.return_value = 2
    provider.get_embedding = AsyncMock(return_value=[1.0, 0.0])
    vec_db = FaissVecDB(
        str(tmp_path / "chunks.db"), str(tmp_path / "index.faiss"), provider
    )
    await kb_db.initialize()
    await kb_db.migrate_to_v1()
    await vec_db.initialize()
    try:
        kb = KnowledgeBase(kb_name="Manuals", embedding_provider_id="test")
        async with kb_db.get_db() as session, session.begin():
            session.add(kb)
            await session.flush()

        documents = []
        for name in ("obsolete.txt", "current.txt"):
            doc = KBDocument(
                kb_id=kb.kb_id,
                doc_name=name,
                file_type="txt",
                file_size=10,
                file_path="",
                chunk_count=1,
            )
            async with kb_db.get_db() as session, session.begin():
                session.add(doc)
                await session.flush()
                session.add(
                    KBMedia(
                        kb_id=kb.kb_id,
                        doc_id=doc.doc_id,
                        media_type="image",
                        file_name=name + ".png",
                        file_path=str(tmp_path / (name + ".png")),
                        file_size=1,
                        mime_type="image/png",
                    )
                )
            await vec_db.insert(
                name,
                {"kb_id": kb.kb_id, "kb_doc_id": doc.doc_id, "chunk_index": 0},
                id=name,
            )
            documents.append(doc)
        target, other = documents

        # Fail at each storage boundary, including a metadata transaction that
        # has deleted media rows but has not yet deleted the document row.
        with monkeypatch.context() as patch:
            if failure_stage == "index_save":
                patch.setattr(
                    vec_db.embedding_storage,
                    "save_index",
                    AsyncMock(side_effect=OSError("injected storage failure")),
                )
            elif failure_stage == "chunk_delete":
                patch.setattr(
                    vec_db.document_storage,
                    "delete_documents",
                    AsyncMock(side_effect=OSError("injected storage failure")),
                )
            else:
                execute = AsyncSession.execute

                async def fail_document_delete(session, statement, *args, **kwargs):
                    if statement.is_delete and statement.table.name == "kb_documents":
                        raise OSError("injected storage failure")
                    return await execute(session, statement, *args, **kwargs)

                patch.setattr(AsyncSession, "execute", fail_document_delete)
            with pytest.raises(OSError, match="injected storage failure"):
                await kb_db.delete_document_by_id(target.doc_id, vec_db)

        # Read through a fresh database connection, as a refreshed document list would.
        await kb_db.close()
        kb_db = KBSQLiteDatabase(str(tmp_path / "kb.db"))
        listed = await kb_db.list_documents_by_kb(kb.kb_id)
        assert {doc.doc_id for doc in listed} == {target.doc_id, other.doc_id}
        assert len(await kb_db.list_media_by_doc(target.doc_id)) == 1
        expected_chunks = 0 if failure_stage == "metadata_delete" else 1
        assert (
            await vec_db.count_documents({"kb_doc_id": target.doc_id})
            == expected_chunks
        )

        await kb_db.delete_document_by_id(target.doc_id, vec_db)
        assert await kb_db.get_document_by_id(target.doc_id) is None
        assert await kb_db.list_media_by_doc(target.doc_id) == []
        assert await vec_db.count_documents({"kb_doc_id": target.doc_id}) == 0
        assert await kb_db.get_document_by_id(other.doc_id) is not None
        assert len(await kb_db.list_media_by_doc(other.doc_id)) == 1
        assert await vec_db.count_documents({"kb_doc_id": other.doc_id}) == 1

        # A restart sees the completed deletion in both chunk and vector stores.
        await vec_db.close()
        vec_db = FaissVecDB(
            str(tmp_path / "chunks.db"), str(tmp_path / "index.faiss"), provider
        )
        await vec_db.initialize()
        assert vec_db.embedding_storage.index.ntotal == 1
        assert await vec_db.count_documents({"kb_doc_id": target.doc_id}) == 0
    finally:
        await vec_db.close()
        await kb_db.close()
