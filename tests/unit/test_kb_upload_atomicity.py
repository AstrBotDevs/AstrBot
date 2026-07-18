"""
Unit tests for knowledge base upload atomicity / compensating rollback.

Covers:
1. insert_batch rolls back document rows when FAISS insert fails
2. upload_document cleans up chunks/vectors/media on storage failure
3. upload_document cleans up after metadata failure (post insert_batch)
4. upload_document does NOT roll back after metadata is committed
5. Real DocumentStorage + EmbeddingStorage leave no orphans on FAISS failure
6. Dimension validation failures never write to DocumentStorage

These tests use lazy imports and a ProviderManager stub to avoid circular
import issues in the astrbot core module chain (same pattern as
test_kb_manager_resilience.py).
"""

import sys
import types
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.db.vec_db.faiss_impl.vec_db import FaissVecDB
from astrbot.core.exceptions import KnowledgeBaseUploadError
from astrbot.core.knowledge_base.models import KnowledgeBase


@pytest.fixture
def stub_provider_manager_module():
    """Stub provider manager module to avoid circular imports in unit tests."""
    original_module = sys.modules.get("astrbot.core.provider.manager")
    stub_module = types.ModuleType("astrbot.core.provider.manager")

    class ProviderManager: ...

    setattr(stub_module, "ProviderManager", ProviderManager)
    sys.modules["astrbot.core.provider.manager"] = stub_module

    # Drop already-imported modules that transitively need ProviderManager so
    # they re-import against the stub.
    to_drop = [
        name
        for name in list(sys.modules)
        if name.startswith("astrbot.core.knowledge_base.kb_helper")
        or name.startswith("astrbot.core.knowledge_base.kb_mgr")
    ]
    for name in to_drop:
        sys.modules.pop(name, None)

    try:
        yield
    finally:
        if original_module is not None:
            sys.modules["astrbot.core.provider.manager"] = original_module
        else:
            sys.modules.pop("astrbot.core.provider.manager", None)


def _make_vec_db() -> FaissVecDB:
    vec_db = FaissVecDB.__new__(FaissVecDB)
    vec_db.embedding_provider = AsyncMock()
    vec_db.document_storage = AsyncMock()
    vec_db.embedding_storage = AsyncMock()
    vec_db.embedding_storage.dimension = 2
    return vec_db


def _import_kb_helper():
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    return KBHelper


def _failing_get_db():
    @asynccontextmanager
    async def _cm():
        raise RuntimeError("kb.db locked")
        yield  # pragma: no cover

    return _cm


def _successful_get_db(session):
    @asynccontextmanager
    async def _cm():
        yield session

    return _cm


def _successful_begin():
    @asynccontextmanager
    async def _cm():
        yield None

    return _cm


def _session_with_begin(execute_side_effect=None):
    """Session mock that supports ``async with session.begin()``."""
    session = MagicMock()
    session.begin = _successful_begin()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock(side_effect=execute_side_effect)
    return session


async def _make_real_vec_db(tmp_path: Path, dim: int = 4) -> FaissVecDB:
    """Build a FaissVecDB backed by real DocumentStorage + EmbeddingStorage."""
    doc_path = str(tmp_path / "doc.db")
    index_path = str(tmp_path / "index.faiss")

    embedding_provider = MagicMock()
    # get_dim is sync in EmbeddingProvider; must return a plain int for FAISS.
    embedding_provider.get_dim = MagicMock(return_value=dim)
    embedding_provider.get_embeddings_batch = AsyncMock()
    embedding_provider.get_embedding = AsyncMock()

    vec_db = FaissVecDB(
        doc_store_path=doc_path,
        index_store_path=index_path,
        embedding_provider=embedding_provider,
    )
    await vec_db.initialize()
    return vec_db


@pytest.mark.asyncio
async def test_insert_batch_rolls_back_documents_when_faiss_fails() -> None:
    """FAISS write failure should delete rows already committed to DocumentStorage."""
    vec_db = _make_vec_db()
    vec_db.embedding_provider.get_embeddings_batch.return_value = [
        [0.1, 0.2],
        [0.3, 0.4],
    ]
    vec_db.document_storage.insert_documents_batch.return_value = [11, 12]
    vec_db.embedding_storage.insert_batch.side_effect = RuntimeError(
        "faiss write failed",
    )

    with pytest.raises(RuntimeError, match="faiss write failed"):
        await FaissVecDB.insert_batch(
            vec_db,
            contents=["chunk-1", "chunk-2"],
            metadatas=[{"kb_doc_id": "doc-1"}, {"kb_doc_id": "doc-1"}],
            ids=["c1", "c2"],
        )

    vec_db.embedding_storage.delete.assert_awaited_once_with([11, 12])
    assert vec_db.document_storage.delete_document_by_doc_id.await_count == 2
    vec_db.document_storage.delete_document_by_doc_id.assert_any_await("c1")
    vec_db.document_storage.delete_document_by_doc_id.assert_any_await("c2")


@pytest.mark.asyncio
async def test_insert_batch_rolls_back_on_int_id_count_mismatch() -> None:
    """Mismatched int_id count after document insert should roll back those docs."""
    vec_db = _make_vec_db()
    vec_db.embedding_provider.get_embeddings_batch.return_value = [
        [0.1, 0.2],
        [0.3, 0.4],
    ]
    vec_db.document_storage.insert_documents_batch.return_value = [11]  # mismatch

    with pytest.raises(KnowledgeBaseUploadError) as exc_info:
        await FaissVecDB.insert_batch(
            vec_db,
            contents=["chunk-1", "chunk-2"],
            metadatas=[{}, {}],
            ids=["c1", "c2"],
        )

    assert "内部 ID 数量" in str(exc_info.value)
    vec_db.embedding_storage.insert_batch.assert_not_awaited()
    vec_db.embedding_storage.delete.assert_awaited_once_with([11])
    assert vec_db.document_storage.delete_document_by_doc_id.await_count == 2


@pytest.mark.asyncio
async def test_insert_batch_dimension_mismatch_does_not_write_documents() -> None:
    """Dimension validation must fail before DocumentStorage is written."""
    vec_db = _make_vec_db()
    vec_db.embedding_storage.dimension = 4
    vec_db.embedding_provider.get_embeddings_batch.return_value = [
        [0.1, 0.2],  # wrong dim
        [0.3, 0.4],
    ]

    with pytest.raises(KnowledgeBaseUploadError) as exc_info:
        await FaissVecDB.insert_batch(
            vec_db,
            contents=["chunk-1", "chunk-2"],
            metadatas=[{}, {}],
            ids=["c1", "c2"],
        )

    assert "维度" in str(exc_info.value)
    vec_db.document_storage.insert_documents_batch.assert_not_awaited()
    vec_db.embedding_storage.insert_batch.assert_not_awaited()


@pytest.mark.asyncio
async def test_insert_batch_real_storage_rolls_back_on_faiss_failure(
    tmp_path: Path,
) -> None:
    """Real DocumentStorage must not keep orphan chunks when FAISS write fails."""
    vec_db = await _make_real_vec_db(tmp_path, dim=4)
    vec_db.embedding_provider.get_embeddings_batch.return_value = [
        [0.1, 0.2, 0.3, 0.4],
        [0.5, 0.6, 0.7, 0.8],
    ]

    original_insert = vec_db.embedding_storage.insert_batch

    async def boom(vectors, ids):
        # Simulate failure after in-memory add would happen: force raise before
        # success so DocumentStorage rows must be cleaned up.
        raise RuntimeError("simulated faiss disk write failure")

    vec_db.embedding_storage.insert_batch = boom  # type: ignore[method-assign]

    kb_doc_id = "kb-doc-real-1"
    with pytest.raises(RuntimeError, match="simulated faiss"):
        await vec_db.insert_batch(
            contents=["alpha chunk", "beta chunk"],
            metadatas=[
                {"kb_id": "kb-1", "kb_doc_id": kb_doc_id, "chunk_index": 0},
                {"kb_id": "kb-1", "kb_doc_id": kb_doc_id, "chunk_index": 1},
            ],
            ids=["chunk-a", "chunk-b"],
        )

    remaining = await vec_db.document_storage.get_documents(
        metadata_filters={"kb_doc_id": kb_doc_id},
        offset=None,
        limit=None,
    )
    assert remaining == []
    assert await vec_db.count_documents(metadata_filter={"kb_doc_id": kb_doc_id}) == 0

    # Restore for clean close; index should still be empty / consistent.
    vec_db.embedding_storage.insert_batch = original_insert  # type: ignore[method-assign]
    await vec_db.close()


@pytest.mark.asyncio
async def test_insert_batch_real_storage_dimension_mismatch_leaves_no_docs(
    tmp_path: Path,
) -> None:
    """Real storage: wrong embedding dim must not leave any document rows."""
    vec_db = await _make_real_vec_db(tmp_path, dim=4)
    vec_db.embedding_provider.get_embeddings_batch.return_value = [
        [0.1, 0.2],  # dim 2 != 4
        [0.3, 0.4],
    ]

    with pytest.raises(KnowledgeBaseUploadError):
        await vec_db.insert_batch(
            contents=["alpha", "beta"],
            metadatas=[
                {"kb_id": "kb-1", "kb_doc_id": "doc-dim", "chunk_index": 0},
                {"kb_id": "kb-1", "kb_doc_id": "doc-dim", "chunk_index": 1},
            ],
            ids=["c1", "c2"],
        )

    remaining = await vec_db.document_storage.get_documents(
        metadata_filters={"kb_doc_id": "doc-dim"},
        offset=None,
        limit=None,
    )
    assert remaining == []
    await vec_db.close()


@pytest.mark.asyncio
async def test_upload_document_cleans_up_on_storage_failure(
    tmp_path: Path,
    stub_provider_manager_module,
) -> None:
    """Storage failure should clean media and request chunk/vector rollback."""
    KBHelper = _import_kb_helper()

    helper = KBHelper.__new__(KBHelper)
    helper.kb = KnowledgeBase(
        kb_name="Test KB",
        description="",
        embedding_provider_id="emb",
    )
    helper.kb_db = MagicMock()
    helper.vec_db = AsyncMock()
    helper.kb_medias_dir = tmp_path / "medias"
    helper.kb_medias_dir.mkdir()
    helper.chunker = AsyncMock()
    helper.chunker.chunk = AsyncMock(return_value=["hello world"])

    media_file = helper.kb_medias_dir / "will-be-set" / "img.png"

    async def fake_save_media(**kwargs):
        nonlocal media_file
        doc_id = kwargs["doc_id"]
        media_dir = helper.kb_medias_dir / doc_id
        media_dir.mkdir(parents=True, exist_ok=True)
        media_file = media_dir / "img.png"
        media_file.write_bytes(b"fake-image")
        media = MagicMock()
        media.file_path = str(media_file)
        return media

    helper._save_media = AsyncMock(side_effect=fake_save_media)
    helper.vec_db.insert_batch.side_effect = RuntimeError("embedding provider down")
    helper.vec_db.delete_documents = AsyncMock()
    helper.kb_db.get_db = _successful_get_db(_session_with_begin())

    parse_result = MagicMock()
    parse_result.text = "hello world"
    parse_result.media = [
        MagicMock(
            media_type="image",
            file_name="img.png",
            content=b"fake-image",
            mime_type="image/png",
        ),
    ]

    with (
        patch(
            "astrbot.core.knowledge_base.kb_helper.select_parser",
            new=AsyncMock(
                return_value=MagicMock(parse=AsyncMock(return_value=parse_result)),
            ),
        ),
        patch.object(helper, "_ensure_vec_db", new=AsyncMock()),
        pytest.raises(KnowledgeBaseUploadError) as exc_info,
    ):
        await helper.upload_document(
            file_name="demo.txt",
            file_content=b"hello world",
            file_type="txt",
        )

    assert exc_info.value.stage == "storage"
    assert "cause" in exc_info.value.details
    helper.vec_db.delete_documents.assert_awaited()
    assert not media_file.exists()


@pytest.mark.asyncio
async def test_upload_document_cleans_up_on_metadata_failure(
    stub_provider_manager_module,
) -> None:
    """Metadata commit failure after insert_batch should delete written chunks."""
    KBHelper = _import_kb_helper()

    helper = KBHelper.__new__(KBHelper)
    helper.kb = KnowledgeBase(
        kb_name="Test KB",
        description="",
        embedding_provider_id="emb",
    )
    helper.kb_db = MagicMock()
    helper.vec_db = AsyncMock()
    helper.kb_medias_dir = Path("/tmp/kb-medias-unused")
    helper.chunker = AsyncMock()

    helper.vec_db.insert_batch = AsyncMock()
    helper.vec_db.delete_documents = AsyncMock()
    helper.kb_db.get_db = _failing_get_db()

    with (
        patch.object(helper, "_ensure_vec_db", new=AsyncMock()),
        pytest.raises(KnowledgeBaseUploadError) as exc_info,
    ):
        await helper.upload_document(
            file_name="demo.txt",
            file_content=None,
            file_type="txt",
            pre_chunked_text=["chunk a", "chunk b"],
        )

    assert exc_info.value.stage == "metadata"
    helper.vec_db.insert_batch.assert_awaited_once()
    helper.vec_db.delete_documents.assert_awaited()


@pytest.mark.asyncio
async def test_upload_document_skips_rollback_after_metadata_commit(
    stub_provider_manager_module,
) -> None:
    """Stats refresh failure after metadata commit must not roll back the doc."""
    KBHelper = _import_kb_helper()

    helper = KBHelper.__new__(KBHelper)
    helper.kb = KnowledgeBase(
        kb_name="Test KB",
        description="",
        embedding_provider_id="emb",
    )
    helper.kb_db = MagicMock()
    helper.vec_db = AsyncMock()
    helper.kb_medias_dir = Path("/tmp/kb-medias-unused")
    helper.chunker = AsyncMock()
    helper.vec_db.insert_batch = AsyncMock()
    helper.vec_db.delete_documents = AsyncMock()
    helper.kb_db.update_kb_stats = AsyncMock(side_effect=RuntimeError("stats fail"))
    helper.refresh_kb = AsyncMock()
    helper.refresh_document = AsyncMock()

    session = _session_with_begin()
    helper.kb_db.get_db = _successful_get_db(session)

    with (
        patch.object(helper, "_ensure_vec_db", new=AsyncMock()),
        pytest.raises(KnowledgeBaseUploadError) as exc_info,
    ):
        await helper.upload_document(
            file_name="demo.txt",
            file_content=None,
            file_type="txt",
            pre_chunked_text=["chunk a"],
        )

    assert exc_info.value.stage == "metadata"
    assert "统计信息刷新失败" in str(exc_info.value)
    helper.vec_db.delete_documents.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_document_skips_rollback_when_refresh_fails_after_commit(
    stub_provider_manager_module,
) -> None:
    """If commit succeeds but session.refresh fails, do not roll back."""
    KBHelper = _import_kb_helper()

    helper = KBHelper.__new__(KBHelper)
    helper.kb = KnowledgeBase(
        kb_name="Test KB",
        description="",
        embedding_provider_id="emb",
    )
    helper.kb_db = MagicMock()
    helper.vec_db = AsyncMock()
    helper.kb_medias_dir = Path("/tmp/kb-medias-unused")
    helper.chunker = AsyncMock()
    helper.vec_db.insert_batch = AsyncMock()
    helper.vec_db.delete_documents = AsyncMock()

    session = _session_with_begin()
    session.refresh = AsyncMock(side_effect=RuntimeError("refresh failed"))
    helper.kb_db.get_db = _successful_get_db(session)

    with (
        patch.object(helper, "_ensure_vec_db", new=AsyncMock()),
        pytest.raises(KnowledgeBaseUploadError) as exc_info,
    ):
        await helper.upload_document(
            file_name="demo.txt",
            file_content=None,
            file_type="txt",
            pre_chunked_text=["chunk a"],
        )

    assert exc_info.value.stage == "metadata"
    assert "文档记录刷新失败" in str(exc_info.value)
    helper.vec_db.delete_documents.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_failed_upload_deletes_vectors_before_metadata(
    tmp_path: Path,
    stub_provider_manager_module,
) -> None:
    """Rollback should delete vectors first, then metadata rows, then media."""
    KBHelper = _import_kb_helper()

    helper = KBHelper.__new__(KBHelper)
    helper.vec_db = AsyncMock()
    helper.kb_db = MagicMock()
    helper.kb_medias_dir = tmp_path / "medias"
    helper.kb_medias_dir.mkdir()

    call_order: list[str] = []

    async def track_delete_documents(**kwargs):
        call_order.append("vectors")

    helper.vec_db.delete_documents = AsyncMock(side_effect=track_delete_documents)

    async def track_execute(*args, **kwargs):
        if "vectors" in call_order and "metadata" not in call_order:
            call_order.append("metadata")
        return None

    helper.kb_db.get_db = _successful_get_db(
        _session_with_begin(execute_side_effect=track_execute),
    )

    media = helper.kb_medias_dir / "doc-x" / "a.png"
    media.parent.mkdir()
    media.write_bytes(b"x")

    await helper._cleanup_failed_upload(doc_id="doc-x", media_paths=[media])

    assert call_order[0] == "vectors"
    assert "metadata" in call_order
    assert not media.exists()
    helper.vec_db.delete_documents.assert_awaited_once_with(
        metadata_filters={"kb_doc_id": "doc-x"},
    )


@pytest.mark.asyncio
async def test_cleanup_failed_upload_is_best_effort(
    tmp_path: Path,
    stub_provider_manager_module,
) -> None:
    """Rollback path failures must not raise; media cleanup still runs."""
    KBHelper = _import_kb_helper()

    helper = KBHelper.__new__(KBHelper)
    helper.kb_db = MagicMock()
    helper.vec_db = AsyncMock()
    helper.vec_db.delete_documents.side_effect = RuntimeError("vec delete failed")
    helper.kb_db.get_db = _failing_get_db()
    helper.kb_medias_dir = tmp_path / "medias"
    helper.kb_medias_dir.mkdir()

    media = helper.kb_medias_dir / "doc-x" / "a.png"
    media.parent.mkdir()
    media.write_bytes(b"x")

    # Should not raise
    await helper._cleanup_failed_upload(doc_id="doc-x", media_paths=[media])
    assert not media.exists()


@pytest.mark.asyncio
async def test_cleanup_failed_upload_real_vec_db_by_kb_doc_id(
    tmp_path: Path,
    stub_provider_manager_module,
) -> None:
    """Cleanup with a real vec_db removes chunks keyed by kb_doc_id."""
    KBHelper = _import_kb_helper()
    vec_db = await _make_real_vec_db(tmp_path, dim=4)
    vec_db.embedding_provider.get_embeddings_batch.return_value = [
        [0.1, 0.2, 0.3, 0.4],
        [0.5, 0.6, 0.7, 0.8],
    ]

    kb_doc_id = "upload-doc-cleanup"
    await vec_db.insert_batch(
        contents=["one", "two"],
        metadatas=[
            {"kb_id": "kb-1", "kb_doc_id": kb_doc_id, "chunk_index": 0},
            {"kb_id": "kb-1", "kb_doc_id": kb_doc_id, "chunk_index": 1},
        ],
        ids=["u1", "u2"],
    )
    assert await vec_db.count_documents(metadata_filter={"kb_doc_id": kb_doc_id}) == 2

    helper = KBHelper.__new__(KBHelper)
    helper.vec_db = vec_db
    helper.kb_db = MagicMock()
    helper.kb_medias_dir = tmp_path / "medias"
    helper.kb_medias_dir.mkdir()
    helper.kb_db.get_db = _successful_get_db(_session_with_begin())

    await helper._cleanup_failed_upload(doc_id=kb_doc_id, media_paths=[])
    assert await vec_db.count_documents(metadata_filter={"kb_doc_id": kb_doc_id}) == 0
    await vec_db.close()
