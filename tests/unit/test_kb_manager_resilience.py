"""
Unit tests for knowledge base manager resilience behavior.

Tests the following scenarios:
1. update_kb preserves old instance when re-initialization fails
2. update_kb switches instance only after new instance initializes successfully
3. _ensure_vec_db clears stale init_error after successful initialization

These tests use lazy imports and mocks to avoid circular import issues
in the astrbot core module chain.
"""

import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def stub_provider_manager_module():
    """Stub provider manager module to avoid circular imports in unit tests."""
    original_module = sys.modules.get("astrbot.core.provider.manager")
    stub_module = types.ModuleType("astrbot.core.provider.manager")

    class ProviderManager: ...

    setattr(stub_module, "ProviderManager", ProviderManager)
    sys.modules["astrbot.core.provider.manager"] = stub_module

    try:
        yield
    finally:
        if original_module is not None:
            sys.modules["astrbot.core.provider.manager"] = original_module
        else:
            sys.modules.pop("astrbot.core.provider.manager", None)


@pytest.fixture
def mock_provider_manager():
    """Create a mock ProviderManager."""
    manager = MagicMock()
    manager.get_provider_by_id = AsyncMock()
    manager.acm = MagicMock()
    manager.acm.default_conf = {}
    return manager


@pytest.fixture
def mock_kb_db():
    """Create a mock KBSQLiteDatabase."""
    db = MagicMock()
    db.get_db = MagicMock()
    db.list_kbs = AsyncMock(return_value=[])
    db.get_kb_by_id = AsyncMock()
    return db


@pytest.fixture
def mock_knowledge_base():
    """Create a mock KnowledgeBase instance."""
    # Use lazy import to avoid circular import
    from astrbot.core.knowledge_base.models import KnowledgeBase

    kb = KnowledgeBase(
        kb_name="test_kb",
        description="Test knowledge base",
        emoji="📚",
        embedding_provider_id="test-embedding-provider",
        rerank_provider_id=None,
        chunk_size=512,
        chunk_overlap=50,
        top_k_dense=50,
        top_k_sparse=50,
        top_m_final=5,
    )
    return kb


@pytest.fixture
def mock_embedding_provider():
    """Create a mock EmbeddingProvider."""
    provider = MagicMock()
    provider.get_embeddings_batch = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
    provider.get_embedding = AsyncMock()
    return provider


@pytest.mark.asyncio
async def test_update_kb_preserves_old_instance_when_reinit_fails(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_knowledge_base,
    mock_embedding_provider,
):
    """
    Test that update_kb preserves the old KBHelper instance when
    re-initialization fails, ensuring the knowledge base remains available.
    """
    # Lazy import to avoid circular import
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    # Setup: create an existing KBHelper with working vec_db
    mock_provider_manager.get_provider_by_id.return_value = mock_embedding_provider

    # Create KBHelper using __new__ to avoid __init__ side effects
    old_helper = KBHelper.__new__(KBHelper)
    old_helper.kb = mock_knowledge_base
    old_helper.prov_mgr = mock_provider_manager
    old_helper.kb_db = mock_kb_db
    old_helper.kb_root_dir = "/tmp/test_kb"
    old_helper.chunker = MagicMock()
    old_helper.init_error = None
    old_helper.vec_db = MagicMock()  # Simulate existing working vec_db
    old_helper.terminate = AsyncMock()

    # Create KBManager and inject the existing helper
    kb_mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    kb_mgr.provider_manager = mock_provider_manager
    kb_mgr.kb_db = mock_kb_db
    kb_mgr.kb_insts = {mock_knowledge_base.kb_id: old_helper}
    kb_mgr.retrieval_manager = MagicMock()

    # Mock KBHelper creation to simulate initialization failure
    with patch.object(KBHelper, "initialize", new_callable=AsyncMock) as mock_init:
        # First call (for new_helper) should fail
        mock_init.side_effect = Exception("Embedding provider unavailable")

        # Execute update_kb with a different embedding provider
        result = await kb_mgr.update_kb(
            kb_id=mock_knowledge_base.kb_id,
            kb_name="updated_kb",
            embedding_provider_id="new-embedding-provider",
        )

        # Verify: the old helper should be returned, not a new one
        assert result is not None
        assert result is old_helper
        assert kb_mgr.kb_insts[mock_knowledge_base.kb_id] is old_helper

        # Verify: old helper's vec_db should still be available
        assert hasattr(result, "vec_db")
        assert result.vec_db is not None

        # Verify: failure does not replace the existing helper state
        assert result.init_error is None
        assert result.kb.kb_name == "test_kb"
        assert result.kb.embedding_provider_id == "test-embedding-provider"


@pytest.mark.asyncio
async def test_update_kb_switches_instance_only_after_new_reinit_success(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_knowledge_base,
    mock_embedding_provider,
):
    """
    Test that update_kb only switches to the new KBHelper instance
    after the new instance successfully initializes.
    """
    # Lazy import to avoid circular import
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    # Setup: create an existing KBHelper
    mock_provider_manager.get_provider_by_id.return_value = mock_embedding_provider

    old_helper = KBHelper.__new__(KBHelper)
    old_helper.kb = mock_knowledge_base
    old_helper.prov_mgr = mock_provider_manager
    old_helper.kb_db = mock_kb_db
    old_helper.kb_root_dir = "/tmp/test_kb"
    old_helper.chunker = MagicMock()
    old_helper.init_error = None
    old_helper.vec_db = MagicMock()
    old_helper.terminate = AsyncMock()

    kb_mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    kb_mgr.provider_manager = mock_provider_manager
    kb_mgr.kb_db = mock_kb_db
    kb_mgr.kb_insts = {mock_knowledge_base.kb_id: old_helper}
    kb_mgr.retrieval_manager = MagicMock()

    # Mock session context for database operations
    mock_session = MagicMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    mock_db_context = MagicMock()
    mock_db_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_db_context.__aexit__ = AsyncMock()
    mock_kb_db.get_db.return_value = mock_db_context

    # Mock KBHelper.initialize to succeed
    with patch.object(KBHelper, "initialize", new_callable=AsyncMock) as mock_init:
        mock_init.return_value = None

        # Execute update_kb
        result = await kb_mgr.update_kb(
            kb_id=mock_knowledge_base.kb_id,
            kb_name="updated_kb",
            embedding_provider_id="new-embedding-provider",
        )

        # Verify: a new helper should be returned
        assert result is not None
        assert result is not old_helper
        assert result.init_error is None
        assert kb_mgr.kb_insts[mock_knowledge_base.kb_id] is result

        # Verify: old helper should be terminated
        old_helper.terminate.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_vec_db_clears_stale_init_error(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_knowledge_base,
    mock_embedding_provider,
):
    """
    Test that _ensure_vec_db clears the init_error attribute
    after successful initialization, removing stale error state.
    """
    # Lazy import to avoid circular import
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    # Setup: create KBHelper with stale init_error
    mock_provider_manager.get_provider_by_id.return_value = mock_embedding_provider

    helper = KBHelper.__new__(KBHelper)
    helper._vec_db_lock = asyncio.Lock()
    helper.kb = mock_knowledge_base
    helper.prov_mgr = mock_provider_manager
    helper.kb_db = mock_kb_db
    helper.kb_root_dir = "/tmp/test_kb"
    helper.chunker = MagicMock()
    helper.init_error = "Previous initialization failed"
    helper.kb_dir = Path("/tmp/test_kb") / mock_knowledge_base.kb_id
    helper.kb_medias_dir = helper.kb_dir / "medias" / mock_knowledge_base.kb_id
    helper.kb_files_dir = helper.kb_dir / "files" / mock_knowledge_base.kb_id

    # Mock FaissVecDB initialization
    mock_vec_db = MagicMock()
    mock_vec_db.initialize = AsyncMock()
    mock_vec_db.close = AsyncMock()

    with patch(
        "astrbot.core.db.vec_db.faiss_impl.vec_db.FaissVecDB",
        return_value=mock_vec_db,
    ):
        # Execute _ensure_vec_db
        await helper._ensure_vec_db()

        # Verify: init_error should be cleared
        assert helper.init_error is None
        assert helper.vec_db is mock_vec_db


@pytest.mark.asyncio
async def test_ensure_vec_db_sets_init_error_on_failure(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_knowledge_base,
):
    """
    Test that _ensure_vec_db does NOT clear init_error when
    initialization fails, preserving the error state.
    """
    # Lazy import to avoid circular import
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    # Setup: provider unavailable
    mock_provider_manager.get_provider_by_id.return_value = None

    helper = KBHelper.__new__(KBHelper)
    helper._vec_db_lock = asyncio.Lock()
    helper.kb = mock_knowledge_base
    helper.prov_mgr = mock_provider_manager
    helper.kb_db = mock_kb_db
    helper.kb_root_dir = "/tmp/test_kb"
    helper.chunker = MagicMock()
    helper.init_error = "Previous initialization failed"
    helper.kb_dir = Path("/tmp/test_kb") / mock_knowledge_base.kb_id
    helper.kb_medias_dir = helper.kb_dir / "medias" / mock_knowledge_base.kb_id
    helper.kb_files_dir = helper.kb_dir / "files" / mock_knowledge_base.kb_id

    # Execute _ensure_vec_db - should raise exception
    try:
        await helper._ensure_vec_db()
        pytest.fail("Expected exception but none was raised")
    except ValueError as e:
        # Verify: exception should be raised
        assert "无法找到" in str(e) or "未配置" in str(e)

        # Verify: init_error should NOT be cleared (still has previous error)
        # Note: _ensure_vec_db doesn't set init_error; that's done by the caller
        assert helper.init_error is not None


@pytest.fixture
def kb_helper(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_knowledge_base,
    mock_embedding_provider,
    tmp_path,
):
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_embedding_provider.get_dim.return_value = 2
    mock_provider_manager.get_provider_by_id.return_value = mock_embedding_provider
    return KBHelper(
        mock_kb_db,
        mock_knowledge_base,
        mock_provider_manager,
        str(tmp_path),
        MagicMock(),
    )


@pytest.mark.asyncio
async def test_concurrent_uploads_preserve_vectors_after_restart(kb_helper, tmp_path):
    import faiss

    from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase

    kb_db = KBSQLiteDatabase(str(tmp_path / "kb.db"))
    await kb_db.initialize()
    kb_helper.kb_db = kb_db
    async with kb_db.get_db() as session, session.begin():
        session.add(kb_helper.kb)

    first_waiting = asyncio.Event()
    release_first = asyncio.Event()
    provider = await kb_helper.get_ep()

    async def embed(texts, **kwargs):
        if texts[0].endswith("document-A"):
            first_waiting.set()
            await release_first.wait()
            return [[1.0, 0.0]]
        return [[0.0, 1.0]]

    provider.get_embeddings_batch.side_effect = embed
    first_vec_db = None
    first_upload = asyncio.create_task(
        kb_helper.upload_document("A.txt", None, "txt", pre_chunked_text=["document-A"])
    )
    try:
        await asyncio.wait_for(first_waiting.wait(), timeout=5)
        first_vec_db = kb_helper.vec_db
        await kb_helper.upload_document(
            "B.txt", None, "txt", pre_chunked_text=["document-B"]
        )
        release_first.set()
        await first_upload

        rows = await kb_helper.vec_db.document_storage.get_documents({}, limit=None)
        assert {row["text"] for row in rows} == {"document-A", "document-B"}
        disk_index = faiss.read_index(str(kb_helper.kb_dir / "index.faiss"))
        assert disk_index.ntotal == 2
        assert kb_helper.vec_db is first_vec_db
        assert kb_helper.vec_db.embedding_storage.index.ntotal == 2
        assert set(faiss.vector_to_array(disk_index.id_map)) == {
            row["id"] for row in rows
        }
        assert await kb_db.count_documents_by_kb(kb_helper.kb.kb_id) == 2

        await kb_helper.terminate()
        await kb_helper.initialize()
        assert kb_helper.vec_db.embedding_storage.index.ntotal == 2
        for query, vector in (
            ("document-A", [1.0, 0.0]),
            ("document-B", [0.0, 1.0]),
        ):
            provider.get_embedding.return_value = vector
            results = await kb_helper.vec_db.retrieve(query, k=1)
            assert results[0].data["text"] == query
    finally:
        release_first.set()
        await asyncio.gather(first_upload, return_exceptions=True)
        await kb_helper.terminate()
        if first_vec_db is not None and first_vec_db is not getattr(
            kb_helper, "vec_db", None
        ):
            await first_vec_db.close()
        await kb_db.close()


@pytest.mark.asyncio
async def test_concurrent_ensure_initializes_one_vec_db(kb_helper):
    started = asyncio.Event()
    release = asyncio.Event()
    vec_db = MagicMock()

    async def initialize():
        started.set()
        await release.wait()

    vec_db.initialize = AsyncMock(side_effect=initialize)
    with patch(
        "astrbot.core.db.vec_db.faiss_impl.vec_db.FaissVecDB",
        return_value=vec_db,
    ) as factory:
        first = asyncio.create_task(kb_helper._ensure_vec_db())
        await asyncio.wait_for(started.wait(), timeout=5)
        second = asyncio.create_task(kb_helper._ensure_vec_db())
        release.set()
        assert await asyncio.gather(first, second) == [vec_db, vec_db]
        factory.assert_called_once()
        vec_db.initialize.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_retries_failed_initialization(kb_helper):
    failed_db, working_db = MagicMock(), MagicMock()
    failed_db.initialize = AsyncMock(side_effect=RuntimeError("init failed"))
    failed_db.close = AsyncMock()
    working_db.initialize = AsyncMock()
    kb_helper.init_error = "Previous initialization failed"
    with patch(
        "astrbot.core.db.vec_db.faiss_impl.vec_db.FaissVecDB",
        side_effect=[failed_db, working_db],
    ) as factory:
        with pytest.raises(RuntimeError, match="init failed"):
            await kb_helper._ensure_vec_db()
        assert getattr(kb_helper, "vec_db", None) is None
        assert kb_helper.init_error is not None
        failed_db.close.assert_awaited_once()
        assert await kb_helper._ensure_vec_db() is working_db
        assert await kb_helper._ensure_vec_db() is working_db
        assert factory.call_count == 2
        assert kb_helper.init_error is None


@pytest.mark.asyncio
async def test_ensure_refreshes_providers_without_reloading_index(kb_helper):
    vec_db = MagicMock()
    vec_db.initialize = AsyncMock()
    with patch(
        "astrbot.core.db.vec_db.faiss_impl.vec_db.FaissVecDB",
        return_value=vec_db,
    ) as factory:
        await kb_helper._ensure_vec_db()
        embedding_provider, rerank_provider = MagicMock(), MagicMock()
        kb_helper.get_ep = AsyncMock(return_value=embedding_provider)
        kb_helper.get_rp = AsyncMock(return_value=rerank_provider)
        assert await kb_helper._ensure_vec_db() is vec_db
        factory.assert_called_once()
        assert vec_db.embedding_provider is embedding_provider
        assert vec_db.rerank_provider is rerank_provider

        kb_helper.get_rp.side_effect = RuntimeError("reranker unavailable")
        await kb_helper._ensure_vec_db()
        assert vec_db.rerank_provider is None

        kb_helper.get_ep.side_effect = ValueError("embedding provider unavailable")
        with pytest.raises(ValueError, match="embedding provider unavailable"):
            await kb_helper._ensure_vec_db()
        assert kb_helper.vec_db is vec_db

        kb_helper.kb.embedding_provider_id = None
        with pytest.raises(ValueError, match="未配置"):
            await kb_helper._ensure_vec_db()
