import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import faiss
import numpy as np
import pytest
import pytest_asyncio
from sqlalchemy.sql.dml import Delete

from astrbot.core.db.vec_db.faiss_impl.embedding_storage import EmbeddingStorage
from astrbot.core.db.vec_db.faiss_impl.vec_db import FaissVecDB
from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
from astrbot.core.knowledge_base.models import KBDocument, KBMedia, KnowledgeBase
from astrbot.dashboard.services.knowledge_base_service import (
    KnowledgeBaseService,
    KnowledgeBaseServiceError,
)


class Embeddings:
    def get_dim(self):
        return 2

    async def get_embeddings_batch(self, contents, **kwargs):
        return [[1.0, 0.0] for _ in contents]


@pytest_asyncio.fixture
async def stores(tmp_path):
    db = KBSQLiteDatabase(str(tmp_path / "kb.db"))
    await db.initialize()
    kb = KnowledgeBase(kb_id="kb", kb_name="Test", embedding_provider_id="test")
    other = KnowledgeBase(kb_id="other", kb_name="Other", embedding_provider_id="test")
    async with db.get_db() as session, session.begin():
        session.add_all([kb, other])
        for doc_id, owner in [("a", "kb"), ("b", "kb"), ("c", "other")]:
            session.add(
                KBDocument(
                    doc_id=doc_id,
                    kb_id=owner,
                    doc_name=doc_id,
                    file_type="txt",
                    file_size=1,
                    file_path="",
                )
            )
            session.add(
                KBMedia(
                    doc_id=doc_id,
                    kb_id=owner,
                    media_id=doc_id,
                    media_type="image",
                    file_name=doc_id,
                    file_path="",
                    file_size=1,
                    mime_type="image/png",
                )
            )
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    helper = KBHelper(
        kb_db=db,
        kb=kb,
        provider_manager=SimpleNamespace(
            get_provider_by_id=AsyncMock(return_value=Embeddings())
        ),
        kb_root_dir=str(tmp_path / "bases"),
        chunker=None,
    )
    vec = await helper._ensure_vec_db()
    await vec.insert_batch(
        ["alpha", "alpha details", "beta", "other"],
        [
            {"kb_id": "kb", "kb_doc_id": "a"},
            {"kb_id": "kb", "kb_doc_id": "a"},
            {"kb_id": "kb", "kb_doc_id": "b"},
            {"kb_id": "other", "kb_doc_id": "c"},
        ],
    )
    helper.refresh_kb = AsyncMock()
    try:
        yield db, vec, helper
    finally:
        await vec.close()
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_batch_deletes_all_chunks_with_one_index_save_and_stats_refresh(stores):
    db, vec, helper = stores
    with (
        patch.object(
            vec.embedding_storage, "save_index", wraps=vec.embedding_storage.save_index
        ) as save,
        patch.object(db, "update_kb_stats", wraps=db.update_kb_stats) as stats,
    ):
        assert await helper.delete_documents(["a", "b", "a"]) == 2
        save.assert_awaited_once()
        stats.assert_awaited_once()
    assert await db.count_documents_by_kb("kb") == 0
    assert await db.list_media_by_doc("a") == []
    assert len(await db.list_media_by_doc("c")) == 1
    assert await vec.count_documents() == 1
    assert vec.embedding_storage.index.ntotal == 1
    assert faiss.read_index(vec.index_store_path).ntotal == 1
    assert await vec.document_storage.search_sparse(["alpha"], limit=10) == []


@pytest.mark.asyncio
async def test_cross_kb_batch_is_rejected_before_any_content_write(stores):
    db, vec, helper = stores
    before = Path(vec.index_store_path).read_bytes()
    with pytest.raises(ValueError, match="不属于"):
        await helper.delete_documents(["a", "c"])
    assert await db.count_documents_by_kb("kb") == 2
    assert Path(vec.index_store_path).read_bytes() == before
    assert await vec.count_documents() == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["vector", "index", "chunks", "metadata"])
async def test_failed_batch_retains_metadata_and_can_be_retried(stores, stage):
    db, vec, helper = stores
    before = Path(vec.index_store_path).read_bytes()
    if stage == "vector":
        failure = patch.object(
            vec.embedding_storage,
            "delete",
            AsyncMock(side_effect=RuntimeError("vector failure")),
        )
    elif stage == "index":
        failure = patch.object(
            vec.embedding_storage,
            "save_index",
            AsyncMock(side_effect=OSError("disk failure")),
        )
    elif stage == "chunks":
        failure = patch.object(
            vec.document_storage,
            "delete_documents",
            AsyncMock(side_effect=RuntimeError("chunks failure")),
        )
    else:
        original = db.get_db

        @asynccontextmanager
        async def failing_session():
            async with original() as session:
                execute = session.execute

                async def injected(statement, *args, **kwargs):
                    if (
                        isinstance(statement, Delete)
                        and statement.table.name == "kb_documents"
                    ):
                        raise RuntimeError("metadata failure")
                    return await execute(statement, *args, **kwargs)

                session.execute = injected
                yield session

        failure = patch.object(db, "get_db", failing_session)
    with failure, pytest.raises((RuntimeError, OSError)):
        await helper.delete_documents(["a", "b"])
    assert await db.count_documents_by_kb("kb") == 2
    assert len(await db.list_media_by_doc("a")) == 1
    if stage in {"vector", "index"}:
        assert Path(vec.index_store_path).read_bytes() == before
    assert await helper.delete_documents(["a", "b"]) == 2
    assert await helper.delete_documents(["a", "b"]) == 0
    assert await vec.count_documents() == 1
    assert faiss.read_index(vec.index_store_path).ntotal == 1


@pytest.mark.asyncio
async def test_single_delete_uses_the_same_retryable_cleanup(stores):
    db, vec, helper = stores
    with (
        patch.object(
            vec.embedding_storage,
            "save_index",
            AsyncMock(side_effect=OSError("disk full")),
        ),
        pytest.raises(OSError),
    ):
        await helper.delete_document("a")
    assert await db.get_document_with_metadata("a") is not None
    await helper.delete_document("a")
    assert await db.get_document_with_metadata("a") is None
    assert await db.get_document_with_metadata("b") is not None


@pytest.mark.asyncio
async def test_upload_waits_for_batch_content_cleanup(stores):
    _, vec, helper = stores
    entered, release = asyncio.Event(), asyncio.Event()
    get_documents = vec.document_storage.get_documents

    async def paused(*args, **kwargs):
        entered.set()
        await release.wait()
        return await get_documents(*args, **kwargs)

    with patch.object(vec.document_storage, "get_documents", paused):
        deleting = asyncio.create_task(helper.delete_documents(["a", "b"]))
        await asyncio.wait_for(entered.wait(), 2)
        uploading = asyncio.create_task(
            vec.insert_batch(["new"], [{"kb_id": "kb", "kb_doc_id": "new"}])
        )
        await asyncio.sleep(0)
        assert not uploading.done()
        release.set()
        await asyncio.wait_for(asyncio.gather(deleting, uploading), 2)
    assert await vec.count_documents() == 2
    assert faiss.read_index(vec.index_store_path).ntotal == 2


def test_partial_index_file_write_never_replaces_existing_file(tmp_path):
    path = tmp_path / "index.faiss"
    index = faiss.IndexIDMap(faiss.IndexFlatL2(2))
    index.add_with_ids(
        np.array([[1, 0]], dtype=np.float32), np.array([1], dtype=np.int64)
    )
    EmbeddingStorage._write_index(index, str(path))
    original = path.read_bytes()

    def fail(_index, destination):
        Path(destination).write_bytes(b"partial")
        raise OSError("disk full")

    with patch("faiss.write_index", fail), pytest.raises(OSError):
        EmbeddingStorage._write_index(index, str(path))
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.asyncio
async def test_service_deduplicates_and_dispatches_one_batch():
    helper = SimpleNamespace(delete_documents=AsyncMock(return_value=2))
    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    service.core_lifecycle = SimpleNamespace(
        kb_manager=SimpleNamespace(get_kb=AsyncMock(return_value=helper))
    )
    data, _ = await service.delete_documents(
        {"kb_id": "kb", "document_ids": ["a", "b", "a"]}
    )
    assert data == {"deleted_count": 2}
    helper.delete_documents.assert_awaited_once_with(["a", "b"])
    for invalid in [[], [""], [1], "a", ["a"] * 501]:
        with pytest.raises(KnowledgeBaseServiceError):
            await service.delete_documents({"kb_id": "kb", "document_ids": invalid})


@pytest.mark.asyncio
async def test_batch_route_validates_payload_and_calls_service_once():
    import httpx
    from fastapi import FastAPI

    from astrbot.dashboard.api.knowledge_bases import (
        get_service,
        require_kb_scope,
        router,
    )

    service = SimpleNamespace(
        delete_documents=AsyncMock(return_value=({"deleted_count": 2}, "done"))
    )
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_service] = lambda: service
    app.dependency_overrides[require_kb_scope] = lambda: None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/knowledge-bases/kb/documents/batch-delete",
            json={"document_ids": ["a", "b"]},
        )
        assert response.status_code == 200
        assert response.json()["data"] == {"deleted_count": 2}
        service.delete_documents.assert_awaited_once_with(
            {"kb_id": "kb", "document_ids": ["a", "b"]}
        )
        response = await client.post(
            "/api/v1/knowledge-bases/kb/documents/batch-delete",
            json={"document_ids": []},
        )
        assert response.status_code == 422
        assert service.delete_documents.await_count == 1


@pytest.mark.asyncio
async def test_batch_cleans_more_than_one_thousand_chunks(stores):
    db, vec, helper = stores
    await vec.insert_batch(
        ["bulk alpha"] * 1100, [{"kb_id": "kb", "kb_doc_id": "a"}] * 1100
    )
    with patch.object(
        vec.embedding_storage, "save_index", wraps=vec.embedding_storage.save_index
    ) as save:
        assert await helper.delete_documents(["a", "b"]) == 2
        save.assert_awaited_once()
    assert await vec.count_documents() == 1
    assert await vec.document_storage.search_sparse(["alpha"], limit=10) == []


@pytest.mark.asyncio
async def test_retry_recovers_chunks_left_by_legacy_metadata_first_deletion(stores):
    from sqlalchemy import delete
    from sqlmodel import col

    db, vec, helper = stores
    async with db.get_db() as session, session.begin():
        await session.execute(delete(KBDocument).where(col(KBDocument.doc_id) == "a"))
    assert await helper.delete_documents(["a", "b"]) == 1
    assert await vec.count_documents() == 1
    assert await db.list_media_by_doc("a") == []


@pytest.mark.asyncio
async def test_statistics_failure_is_retryable_after_content_cleanup(stores):
    db, _, helper = stores
    with (
        patch.object(
            db, "update_kb_stats", AsyncMock(side_effect=RuntimeError("stats failure"))
        ),
        pytest.raises(RuntimeError),
    ):
        await helper.delete_documents(["a", "b"])
    assert await helper.delete_documents(["a", "b"]) == 0
    async with db.get_db() as session:
        from sqlalchemy import select
        from sqlmodel import col

        result = await session.execute(
            select(KnowledgeBase).where(col(KnowledgeBase.kb_id) == "kb")
        )
        kb = result.scalar_one()
        assert (kb.doc_count, kb.chunk_count) == (0, 0)


@pytest.mark.asyncio
async def test_repeated_ensure_reuses_index_without_losing_uploaded_vectors(stores):
    _, vec, helper = stores
    second = await helper._ensure_vec_db()
    assert second is vec
    await vec.insert_batch(["new"], [{"kb_id": "kb", "kb_doc_id": "new"}])
    await helper.delete_documents(["a", "b"])
    assert helper.vec_db is vec
    assert await vec.count_documents() == 2
    assert vec.embedding_storage.index.ntotal == 2
    assert faiss.read_index(vec.index_store_path).ntotal == 2


@pytest.mark.asyncio
async def test_concurrent_first_ensure_initializes_once(stores, tmp_path):
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    db, _, existing = stores
    helper = KBHelper(db, existing.kb, existing.prov_mgr, str(tmp_path / "cold"), None)
    entered, release = asyncio.Event(), asyncio.Event()
    initialize = FaissVecDB.initialize
    instances = []

    async def paused(vec):
        instances.append(vec)
        entered.set()
        await release.wait()
        await initialize(vec)

    try:
        with patch.object(FaissVecDB, "initialize", paused):
            first = asyncio.create_task(helper._ensure_vec_db())
            await asyncio.wait_for(entered.wait(), 2)
            second = asyncio.create_task(helper._ensure_vec_db())
            await asyncio.sleep(0)
            release.set()
            one, two = await asyncio.wait_for(asyncio.gather(first, second), 5)
        assert one is two
        assert len(instances) == 1
    finally:
        release.set()
        await helper.terminate()


@pytest.mark.asyncio
async def test_failed_initialization_can_be_attempted_again(stores, tmp_path):
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    db, _, existing = stores
    helper = KBHelper(db, existing.kb, existing.prov_mgr, str(tmp_path / "retry"), None)
    helper.init_error = "Provider unavailable"
    with patch.object(
        helper, "get_ep", AsyncMock(side_effect=ValueError("unavailable"))
    ):
        with pytest.raises(ValueError, match="unavailable"):
            await helper._ensure_vec_db()
    assert not hasattr(helper, "vec_db")
    assert helper.init_error == "Provider unavailable"
    try:
        vec = await helper._ensure_vec_db()
        assert helper.init_error is None
        assert await helper._ensure_vec_db() is vec
    finally:
        await helper.terminate()


@pytest.mark.asyncio
async def test_upload_and_delete_share_real_initialized_store(stores):
    db, vec, helper = stores
    entered, release = asyncio.Event(), asyncio.Event()
    embed = vec.embedding_provider.get_embeddings_batch

    async def paused(contents, **kwargs):
        entered.set()
        await release.wait()
        return await embed(contents, **kwargs)

    with patch.object(vec.embedding_provider, "get_embeddings_batch", paused):
        uploading = asyncio.create_task(
            helper.upload_document(
                file_name="new.txt",
                file_content=None,
                file_type="txt",
                pre_chunked_text=["new content"],
            )
        )
        try:
            await asyncio.wait_for(entered.wait(), 2)
            await helper.delete_documents(["a", "b"])
        finally:
            release.set()
        document = await asyncio.wait_for(uploading, 5)
    assert helper.vec_db is vec
    assert await db.get_document_with_metadata(document.doc_id) is not None
    assert await vec.count_documents() == 2
    assert vec.embedding_storage.index.ntotal == 2
    assert faiss.read_index(vec.index_store_path).ntotal == 2
