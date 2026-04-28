"""
Unit tests for knowledge base manager resilience behavior.

Tests the following scenarios:
1. update_kb surfaces re-initialization failures while preserving the old helper
2. update_kb switches instance only after new instance initializes successfully
3. _ensure_vec_db clears stale init_error after successful initialization

These tests use lazy imports and mocks to avoid circular import issues
in the astrbot core module chain.
"""

import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.exceptions import KnowledgeBaseUploadError


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
async def test_update_kb_raises_error_and_preserves_old_instance_when_reinit_fails(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_knowledge_base,
    mock_embedding_provider,
):
    """
    Test that update_kb surfaces re-initialization failures while
    preserving the old KBHelper instance for continued availability.
    """
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

    with patch.object(KBHelper, "initialize", new_callable=AsyncMock) as mock_init:
        mock_init.side_effect = Exception("Embedding provider unavailable")

        with pytest.raises(KnowledgeBaseUploadError) as exc_info:
            await kb_mgr.update_kb(
                kb_id=mock_knowledge_base.kb_id,
                kb_name="updated_kb",
                embedding_provider_id="new-embedding-provider",
            )

    assert "Embedding provider unavailable" in str(exc_info.value)
    assert kb_mgr.kb_insts[mock_knowledge_base.kb_id] is old_helper
    assert hasattr(old_helper, "vec_db")
    assert old_helper.vec_db is not None
    assert old_helper.init_error is None
    assert old_helper.kb.kb_name == "test_kb"
    assert old_helper.kb.embedding_provider_id == "test-embedding-provider"


@pytest.mark.asyncio
async def test_update_kb_raises_user_facing_error_for_dimension_mismatch(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_knowledge_base,
    mock_embedding_provider,
):
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

    with patch.object(KBHelper, "initialize", new_callable=AsyncMock) as mock_init:
        mock_init.side_effect = KnowledgeBaseUploadError(
            stage="embedding",
            user_message="知识库索引维度与当前嵌入模型维度不一致",
            details={"index_dimension": 768, "provider_dimension": 1536},
        )

        with pytest.raises(ValueError) as exc_info:
            await kb_mgr.update_kb(
                kb_id=mock_knowledge_base.kb_id,
                kb_name="updated_kb",
                embedding_provider_id="new-embedding-provider",
            )

    assert exc_info.value.stage == "embedding"
    assert "知识库索引维度与当前嵌入模型维度不一致" in str(exc_info.value)
    assert kb_mgr.kb_insts[mock_knowledge_base.kb_id] is old_helper
    assert old_helper.kb.kb_name == "test_kb"
    assert old_helper.kb.embedding_provider_id == "test-embedding-provider"


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

    mock_session = MagicMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    mock_db_context = MagicMock()
    mock_db_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_db_context.__aexit__ = AsyncMock()
    mock_kb_db.get_db.return_value = mock_db_context

    with patch.object(KBHelper, "initialize", new_callable=AsyncMock) as mock_init:
        mock_init.return_value = None

        result = await kb_mgr.update_kb(
            kb_id=mock_knowledge_base.kb_id,
            kb_name="updated_kb",
            embedding_provider_id="new-embedding-provider",
        )

    assert result is not None
    assert result is not old_helper
    assert result.init_error is None
    assert kb_mgr.kb_insts[mock_knowledge_base.kb_id] is result
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
    from astrbot.core.knowledge_base.kb_helper import KBHelper

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

    mock_vec_db = MagicMock()
    mock_vec_db.initialize = AsyncMock()
    mock_vec_db.close = AsyncMock()

    with patch(
        "astrbot.core.db.vec_db.faiss_impl.vec_db.FaissVecDB",
        return_value=mock_vec_db,
    ):
        await helper._ensure_vec_db()

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
    from astrbot.core.knowledge_base.kb_helper import KBHelper

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

    try:
        await helper._ensure_vec_db()
        pytest.fail("Expected exception but none was raised")
    except ValueError as e:
        assert "无法找到" in str(e) or "未配置" in str(e)
        assert helper.init_error is not None
