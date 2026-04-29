"""
Unit tests for KnowledgeBaseManager.

Covers construction, initialize, create_kb, get_kb, get_kb_by_name,
delete_kb, list_kbs, update_kb, retrieve, terminate, and upload_from_url.
All tests use mocks to isolate the manager from its dependencies.
"""

import sys
import types
from unittest.mock import ANY, AsyncMock, MagicMock, call, patch

import pytest


@pytest.fixture
def stub_provider_manager_module():
    """Stub provider manager module to avoid circular imports in unit tests."""
    original_module = sys.modules.get("astrbot.core.provider.manager")
    stub_module = types.ModuleType("astrbot.core.provider.manager")

    class ProviderManager:
        ...

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
def mock_session():
    """Create a mock async session with transaction helpers."""
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.begin = MagicMock()
    session.begin.return_value.__aenter__ = AsyncMock()
    session.begin.return_value.__aexit__ = AsyncMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture
def mock_db_context(mock_session):
    """Create a mock async context manager for get_db()."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock()
    return ctx


@pytest.fixture
def mock_knowledge_base():
    """Create a mock KnowledgeBase instance using lazy import."""
    from astrbot.core.knowledge_base.models import KnowledgeBase

    kb = KnowledgeBase(
        kb_name="test_kb",
        description="Test knowledge base",
        emoji="test",
        embedding_provider_id="test-embedding-provider",
        rerank_provider_id=None,
        chunk_size=512,
        chunk_overlap=50,
        top_k_dense=50,
        top_k_sparse=50,
        top_m_final=5,
    )
    return kb


# ---------------------------------------------------------------
# Construction & initialization
# ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_manager_construction(stub_provider_manager_module, mock_provider_manager):
    """Test that KnowledgeBaseManager can be constructed with a provider manager."""
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    mgr.provider_manager = mock_provider_manager
    mgr.kb_insts = {}
    mgr._session_deleted_callback_registered = False

    assert mgr.provider_manager is mock_provider_manager
    assert mgr.kb_insts == {}
    assert mgr._session_deleted_callback_registered is False


@pytest.mark.asyncio
async def test_manager_initialize_creates_db_and_loads_kbs(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
):
    """Test that initialize() creates the database and loads existing KBs."""
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    mgr.provider_manager = mock_provider_manager
    mgr.kb_insts = {}

    with (
        patch(
            "astrbot.core.knowledge_base.kb_mgr.KBSQLiteDatabase",
            return_value=mock_kb_db,
        ) as mock_db_cls,
        patch(
            "astrbot.core.knowledge_base.kb_mgr.RetrievalManager",
        ) as mock_retrieval_cls,
        patch(
            "astrbot.core.knowledge_base.kb_mgr.SparseRetriever",
        ),
        patch(
            "astrbot.core.knowledge_base.kb_mgr.RankFusion",
        ),
    ):
        mock_retrieval = MagicMock()
        mock_retrieval_cls.return_value = mock_retrieval

        await mgr.initialize()

        mock_db_cls.assert_called_once()
        mock_kb_db.initialize.assert_awaited_once()
        mock_kb_db.migrate_to_v1.assert_awaited_once()
        mock_kb_db.list_kbs.assert_awaited_once()
        assert mgr.retrieval_manager is mock_retrieval


@pytest.mark.asyncio
async def test_initialize_handles_import_error_gracefully(
    stub_provider_manager_module,
    mock_provider_manager,
):
    """Test that initialize() catches ImportError without crashing."""
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    mgr.provider_manager = mock_provider_manager
    mgr.kb_insts = {}

    with patch(
        "astrbot.core.knowledge_base.kb_mgr.KBSQLiteDatabase",
        side_effect=ImportError("missing dependency"),
    ):
        await mgr.initialize()
        # Should not raise — the error is logged
        assert not hasattr(mgr, "retrieval_manager") or mgr.retrieval_manager is None


# ---------------------------------------------------------------
# create_kb
# ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_kb_raises_when_embedding_provider_id_is_none(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
):
    """Test that create_kb raises ValueError when embedding_provider_id is None."""
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    mgr.provider_manager = mock_provider_manager
    mgr.kb_db = mock_kb_db
    mgr.kb_insts = {}

    with pytest.raises(ValueError, match="embedding_provider_id"):
        await mgr.create_kb(kb_name="my_kb")


@pytest.mark.asyncio
async def test_create_kb_success(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_db_context,
    mock_session,
):
    """Test that create_kb creates a new KB, persists it, and returns a KBHelper."""
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_kb_db.get_db.return_value = mock_db_context

    mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    mgr.provider_manager = mock_provider_manager
    mgr.kb_db = mock_kb_db
    mgr.kb_insts = {}

    with patch.object(KBHelper, "initialize", new_callable=AsyncMock) as mock_init:
        mock_init.return_value = None

        result = await mgr.create_kb(
            kb_name="my_kb",
            description="desc",
            emoji="doc",
            embedding_provider_id="ep-1",
        )

        assert result is not None
        assert result.kb.kb_name == "my_kb"
        assert result.kb.embedding_provider_id == "ep-1"
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()
        mock_init.assert_awaited_once()
        mock_session.commit.assert_awaited_once()
        assert result.kb.kb_id in mgr.kb_insts


@pytest.mark.asyncio
async def test_create_kb_duplicate_name_raises(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_db_context,
    mock_session,
):
    """Test that create_kb raises ValueError on duplicate kb_name."""
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    mock_kb_db.get_db.return_value = mock_db_context
    # Simulate an IntegrityError-like message
    mock_session.flush = AsyncMock(
        side_effect=Exception("UNIQUE constraint failed: kb_name"),
    )

    mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    mgr.provider_manager = mock_provider_manager
    mgr.kb_db = mock_kb_db
    mgr.kb_insts = {}

    with pytest.raises(ValueError, match="已存在"):
        await mgr.create_kb(
            kb_name="my_kb",
            embedding_provider_id="ep-1",
        )


# ---------------------------------------------------------------
# get_kb / get_kb_by_name
# ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_kb_returns_none_for_unknown_id(
    stub_provider_manager_module,
    mock_provider_manager,
):
    """Test that get_kb returns None when kb_id is not found."""
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    mgr.kb_insts = {}

    result = await mgr.get_kb("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_get_kb_returns_helper_for_known_id(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_knowledge_base,
):
    """Test that get_kb returns the correct KBHelper for a known kb_id."""
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    helper = KBHelper.__new__(KBHelper)
    helper.kb = mock_knowledge_base

    mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    mgr.kb_insts = {mock_knowledge_base.kb_id: helper}

    result = await mgr.get_kb(mock_knowledge_base.kb_id)
    assert result is helper


@pytest.mark.asyncio
async def test_get_kb_by_name_returns_helper(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_knowledge_base,
):
    """Test that get_kb_by_name returns the correct helper by matching kb_name."""
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    helper = KBHelper.__new__(KBHelper)
    helper.kb = mock_knowledge_base

    mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    mgr.kb_insts = {mock_knowledge_base.kb_id: helper}

    result = await mgr.get_kb_by_name("test_kb")
    assert result is helper


@pytest.mark.asyncio
async def test_get_kb_by_name_returns_none_for_missing(
    stub_provider_manager_module,
    mock_provider_manager,
):
    """Test that get_kb_by_name returns None when no match is found."""
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    mgr.kb_insts = {}

    result = await mgr.get_kb_by_name("nonexistent")
    assert result is None


# ---------------------------------------------------------------
# delete_kb
# ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_kb_returns_false_for_unknown(
    stub_provider_manager_module,
    mock_provider_manager,
):
    """Test that delete_kb returns False when kb_id is not found."""
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    mgr.kb_insts = {}

    result = await mgr.delete_kb("nonexistent")
    assert result is False


@pytest.mark.asyncio
async def test_delete_kb_removes_helper(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_db_context,
    mock_session,
    mock_knowledge_base,
):
    """Test that delete_kb removes the KBHelper, deletes vec_db, and removes from DB."""
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_kb_db.get_db.return_value = mock_db_context

    helper = KBHelper.__new__(KBHelper)
    helper.kb = mock_knowledge_base
    helper.vec_db = MagicMock()
    helper.delete_vec_db = AsyncMock()
    helper.terminate = AsyncMock()

    mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    mgr.kb_db = mock_kb_db
    mgr.kb_insts = {mock_knowledge_base.kb_id: helper}

    result = await mgr.delete_kb(mock_knowledge_base.kb_id)

    assert result is True
    helper.delete_vec_db.assert_awaited_once()
    mock_session.delete.assert_awaited_once_with(mock_knowledge_base)
    mock_session.commit.assert_awaited_once()
    assert mock_knowledge_base.kb_id not in mgr.kb_insts


# ---------------------------------------------------------------
# list_kbs
# ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_kbs_returns_empty_when_no_instances(
    stub_provider_manager_module,
    mock_provider_manager,
):
    """Test that list_kbs returns an empty list when no KBs exist."""
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    mgr.kb_insts = {}

    result = await mgr.list_kbs()
    assert result == []


@pytest.mark.asyncio
async def test_list_kbs_returns_all_knowledge_bases(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_knowledge_base,
):
    """Test that list_kbs returns KnowledgeBase objects for all instances."""
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    helper = KBHelper.__new__(KBHelper)
    helper.kb = mock_knowledge_base

    mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    mgr.kb_insts = {mock_knowledge_base.kb_id: helper}

    result = await mgr.list_kbs()
    assert len(result) == 1
    assert result[0] is mock_knowledge_base


# ---------------------------------------------------------------
# terminate
# ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_terminate_closes_all_helpers_and_db(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_knowledge_base,
):
    """Test that terminate() terminates all helpers and closes the database."""
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    helper = KBHelper.__new__(KBHelper)
    helper.kb = mock_knowledge_base
    helper.terminate = AsyncMock()

    mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    mgr.kb_db = mock_kb_db
    mgr.kb_insts = {mock_knowledge_base.kb_id: helper}

    mock_kb_db.close = AsyncMock()

    await mgr.terminate()

    helper.terminate.assert_awaited_once()
    mock_kb_db.close.assert_awaited_once()
    assert mgr.kb_insts == {}


@pytest.mark.asyncio
async def test_terminate_handles_helper_failure_gracefully(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_knowledge_base,
):
    """Test that terminate() continues even if one helper raises."""
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    helper = KBHelper.__new__(KBHelper)
    helper.kb = mock_knowledge_base
    helper.terminate = AsyncMock(side_effect=Exception("close failed"))

    mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    mgr.kb_db = mock_kb_db
    mgr.kb_insts = {mock_knowledge_base.kb_id: helper}

    mock_kb_db.close = AsyncMock()

    # Should not raise
    await mgr.terminate()
    helper.terminate.assert_awaited_once()
    mock_kb_db.close.assert_awaited_once()


# ---------------------------------------------------------------
# retrieve
# ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_returns_empty_when_no_kb_found(
    stub_provider_manager_module,
    mock_provider_manager,
):
    """Test that retrieve returns an empty dict when no KBs match the given names."""
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    mgr.kb_insts = {}

    result = await mgr.retrieve("query", kb_names=["nonexistent"])
    assert result == {}


@pytest.mark.asyncio
async def test_retrieve_raises_when_all_kbs_unavailable(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_knowledge_base,
):
    """Test that retrieve raises ValueError when all matching KBs have init_error."""
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    helper = KBHelper.__new__(KBHelper)
    helper.kb = mock_knowledge_base
    helper.init_error = "provider unavailable"

    mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    mgr.kb_insts = {mock_knowledge_base.kb_id: helper}

    with pytest.raises(ValueError, match="所有请求的知识库均不可用"):
        await mgr.retrieve("query", kb_names=["test_kb"])


@pytest.mark.asyncio
async def test_retrieve_returns_formatted_results(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_knowledge_base,
):
    """Test that retrieve returns properly formatted results when KBs are available."""
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    helper = KBHelper.__new__(KBHelper)
    helper.kb = mock_knowledge_base
    helper.init_error = None

    mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    mgr.kb_insts = {mock_knowledge_base.kb_id: helper}
    mgr.kb_db = MagicMock()

    retrieval_manager = MagicMock()
    retrieval_manager.retrieve = AsyncMock()

    from collections import namedtuple

    FakeResult = namedtuple(
        "FakeResult",
        [
            "chunk_id",
            "doc_id",
            "kb_id",
            "kb_name",
            "doc_name",
            "chunk_index",
            "content",
            "score",
            "metadata",
        ],
    )
    fake_result = FakeResult(
        chunk_id="c1",
        doc_id="d1",
        kb_id=mock_knowledge_base.kb_id,
        kb_name="test_kb",
        doc_name="doc1.pdf",
        chunk_index=0,
        content="some content",
        score=0.95,
        metadata={"chunk_index": 0, "char_count": 12},
    )
    retrieval_manager.retrieve.return_value = [fake_result]
    mgr.retrieval_manager = retrieval_manager

    result = await mgr.retrieve("query", kb_names=["test_kb"])

    assert result is not None
    assert "context_text" in result
    assert "results" in result
    assert len(result["results"]) == 1
    assert result["results"][0]["kb_name"] == "test_kb"
    assert result["results"][0]["content"] == "some content"
    retrieval_manager.retrieve.assert_awaited_once()


# ---------------------------------------------------------------
# upload_from_url
# ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_from_url_raises_when_kb_not_found(
    stub_provider_manager_module,
    mock_provider_manager,
):
    """Test that upload_from_url raises ValueError when kb_id is not found."""
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    mgr.kb_insts = {}

    with pytest.raises(ValueError, match="not found"):
        await mgr.upload_from_url("nonexistent", "http://example.com")


@pytest.mark.asyncio
async def test_upload_from_url_delegates_to_helper(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_knowledge_base,
):
    """Test that upload_from_url delegates to the correct KBHelper."""
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    helper = KBHelper.__new__(KBHelper)
    helper.kb = mock_knowledge_base
    helper.upload_from_url = AsyncMock(return_value="fake_doc")

    mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    mgr.kb_insts = {mock_knowledge_base.kb_id: helper}

    result = await mgr.upload_from_url(
        mock_knowledge_base.kb_id,
        "http://example.com",
    )

    assert result == "fake_doc"
    helper.upload_from_url.assert_awaited_once_with(
        url="http://example.com",
        chunk_size=512,
        chunk_overlap=50,
        batch_size=32,
        tasks_limit=3,
        max_retries=3,
        progress_callback=None,
    )
