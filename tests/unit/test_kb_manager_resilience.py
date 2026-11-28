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


@pytest.mark.asyncio
async def test_ensure_vec_db_reuses_instance_and_closes_superseded(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_knowledge_base,
    mock_embedding_provider,
):
    """_ensure_vec_db should reuse an active vec_db and close old ones when replaced."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    second_provider = MagicMock()
    mock_provider_manager.get_provider_by_id = AsyncMock(
        side_effect=[mock_embedding_provider, mock_embedding_provider, second_provider]
    )

    helper = KBHelper.__new__(KBHelper)
    helper.kb = mock_knowledge_base
    helper.prov_mgr = mock_provider_manager
    helper.kb_db = mock_kb_db
    helper.kb_root_dir = "/tmp/test_kb"
    helper.chunker = MagicMock()
    helper.init_error = None
    helper.kb_dir = Path("/tmp/test_kb") / mock_knowledge_base.kb_id
    helper.kb_medias_dir = helper.kb_dir / "medias" / mock_knowledge_base.kb_id
    helper.kb_files_dir = helper.kb_dir / "files" / mock_knowledge_base.kb_id

    first_vec_db = MagicMock()
    first_vec_db.initialize = AsyncMock()
    first_vec_db.close = AsyncMock()
    first_vec_db.embedding_provider = mock_embedding_provider
    first_vec_db.rerank_provider = None

    second_vec_db = MagicMock()
    second_vec_db.initialize = AsyncMock()
    second_vec_db.close = AsyncMock()
    second_vec_db.embedding_provider = second_provider
    second_vec_db.rerank_provider = None

    with patch(
        "astrbot.core.db.vec_db.faiss_impl.vec_db.FaissVecDB",
        side_effect=[first_vec_db, second_vec_db],
    ) as mock_cls:
        res1 = await helper._ensure_vec_db()
        res2 = await helper._ensure_vec_db()
        assert res1 is first_vec_db
        assert res2 is first_vec_db
        assert mock_cls.call_count == 1
        first_vec_db.close.assert_not_awaited()

        res3 = await helper._ensure_vec_db()
        assert res3 is second_vec_db
        assert mock_cls.call_count == 2
        first_vec_db.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_kb_cleans_up_helper_when_commit_fails(
    tmp_path: Path,
    monkeypatch,
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
):
    """create_kb should delete initialized helper storage if commit fails."""
    from astrbot.core.knowledge_base import kb_mgr as kb_mgr_module
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    monkeypatch.setattr(kb_mgr_module, "FILES_PATH", str(tmp_path))
    mock_kb_db.get_kb_by_name = AsyncMock(return_value=None)

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock(side_effect=RuntimeError("commit failed"))
    mock_db_context = MagicMock()
    mock_db_context.__aenter__ = AsyncMock(return_value=session)
    mock_db_context.__aexit__ = AsyncMock(return_value=False)
    mock_kb_db.get_db.return_value = mock_db_context

    kb_mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    kb_mgr.provider_manager = mock_provider_manager
    kb_mgr.kb_db = mock_kb_db
    kb_mgr.kb_insts = {}
    kb_mgr.retrieval_manager = MagicMock()

    mock_vec_db = MagicMock()
    mock_vec_db.initialize = AsyncMock()
    mock_vec_db.close = AsyncMock()

    with (
        patch(
            "astrbot.core.db.vec_db.faiss_impl.vec_db.FaissVecDB",
            return_value=mock_vec_db,
        ),
        pytest.raises(RuntimeError, match="commit failed"),
    ):
        await kb_mgr.create_kb(
            kb_name="new_kb",
            embedding_provider_id="emb-1",
        )

    mock_vec_db.close.assert_awaited_once()
    assert kb_mgr.kb_insts == {}
    assert not any(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_update_kb_rolls_back_state_and_terminates_new_helper_on_commit_error(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_knowledge_base,
    mock_embedding_provider,
):
    """update_kb should roll back in-memory fields and close new_helper on DB failure."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

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

    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock(side_effect=RuntimeError("db write failed"))
    session.refresh = AsyncMock()
    mock_db_context = MagicMock()
    mock_db_context.__aenter__ = AsyncMock(return_value=session)
    mock_db_context.__aexit__ = AsyncMock(return_value=False)
    mock_kb_db.get_db.return_value = mock_db_context

    mock_new_vec_db = MagicMock()
    mock_new_vec_db.initialize = AsyncMock()
    mock_new_vec_db.close = AsyncMock()

    with (
        patch(
            "astrbot.core.db.vec_db.faiss_impl.vec_db.FaissVecDB",
            return_value=mock_new_vec_db,
        ),
        pytest.raises(RuntimeError, match="db write failed"),
    ):
        await kb_mgr.update_kb(
            kb_id=mock_knowledge_base.kb_id,
            kb_name="renamed_kb",
            embedding_provider_id="new-emb",
        )

    assert mock_knowledge_base.kb_name == "test_kb"
    assert mock_knowledge_base.embedding_provider_id == "test-embedding-provider"
    assert kb_mgr.kb_insts[mock_knowledge_base.kb_id] is old_helper
    mock_new_vec_db.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_kb_keeps_committed_helper_when_refresh_fails(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_knowledge_base,
    mock_embedding_provider,
):
    """Post-commit session.refresh failure must not roll back update_kb."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

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

    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock(side_effect=RuntimeError("refresh failed"))
    mock_db_context = MagicMock()
    mock_db_context.__aenter__ = AsyncMock(return_value=session)
    mock_db_context.__aexit__ = AsyncMock(return_value=False)
    mock_kb_db.get_db.return_value = mock_db_context

    with patch.object(KBHelper, "initialize", new_callable=AsyncMock):
        new_helper = await kb_mgr.update_kb(
            kb_id=mock_knowledge_base.kb_id,
            kb_name="renamed_kb",
            embedding_provider_id="new-emb",
        )

    assert new_helper is not None
    assert new_helper is not old_helper
    assert kb_mgr.kb_insts[mock_knowledge_base.kb_id] is new_helper
    assert old_helper._superseded is True
    old_helper.terminate.assert_awaited_once()
    assert mock_knowledge_base.kb_name == "renamed_kb"


@pytest.mark.asyncio
async def test_update_kb_rethrows_cancelled_error_during_initialize(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_knowledge_base,
):
    """CancelledError during new_helper.initialize should roll back and propagate."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    old_helper = KBHelper.__new__(KBHelper)
    old_helper.kb = mock_knowledge_base
    old_helper.prov_mgr = mock_provider_manager
    old_helper.kb_db = mock_kb_db
    old_helper.kb_root_dir = "/tmp/test_kb"
    old_helper.chunker = MagicMock()
    old_helper.init_error = None
    old_helper.vec_db = MagicMock()

    kb_mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    kb_mgr.provider_manager = mock_provider_manager
    kb_mgr.kb_db = mock_kb_db
    kb_mgr.kb_insts = {mock_knowledge_base.kb_id: old_helper}
    kb_mgr.retrieval_manager = MagicMock()

    with (
        patch.object(
            KBHelper,
            "initialize",
            new_callable=AsyncMock,
            side_effect=asyncio.CancelledError(),
        ),
        patch.object(KBHelper, "terminate", new_callable=AsyncMock) as mock_term,
        pytest.raises(asyncio.CancelledError),
    ):
        await kb_mgr.update_kb(
            kb_id=mock_knowledge_base.kb_id,
            kb_name="renamed_kb",
        )

    assert mock_knowledge_base.kb_name == "test_kb"
    assert kb_mgr.kb_insts[mock_knowledge_base.kb_id] is old_helper
    mock_term.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_vec_db_closes_vec_db_on_cancelled_initialize(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_knowledge_base,
    mock_embedding_provider,
):
    """_ensure_vec_db should close a newly created vec_db if initialize is cancelled."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_provider_manager.get_provider_by_id = AsyncMock(
        return_value=mock_embedding_provider
    )
    helper = KBHelper.__new__(KBHelper)
    helper.kb = mock_knowledge_base
    helper.prov_mgr = mock_provider_manager
    helper.kb_db = mock_kb_db
    helper.kb_root_dir = "/tmp/test_kb"
    helper.chunker = MagicMock()
    helper.init_error = None
    helper.kb_dir = Path("/tmp/test_kb") / mock_knowledge_base.kb_id
    helper.kb_medias_dir = helper.kb_dir / "medias" / mock_knowledge_base.kb_id
    helper.kb_files_dir = helper.kb_dir / "files" / mock_knowledge_base.kb_id

    vec_db = MagicMock()
    vec_db.initialize = AsyncMock(side_effect=asyncio.CancelledError())
    vec_db.close = AsyncMock()

    with (
        patch(
            "astrbot.core.db.vec_db.faiss_impl.vec_db.FaissVecDB",
            return_value=vec_db,
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        await helper._ensure_vec_db()

    vec_db.close.assert_awaited_once()
