"""
Unit tests for KBHelper.

Covers construction, initialize, get_ep, get_rp, _ensure_vec_db, terminate,
delete_vec_db, upload_document, list_documents, get_document, delete_document,
delete_chunk, refresh_kb, refresh_document, get_chunks_by_doc_id,
get_chunk_count_by_doc_id, _save_media, upload_from_url,
and _clean_and_rechunk_content.
All tests use mocks to isolate KBHelper from its dependencies.
"""

import json
import sys
import types
from pathlib import Path
from unittest.mock import ANY, AsyncMock, MagicMock, PropertyMock, call, patch

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
    db.list_documents_by_kb = AsyncMock(return_value=[])
    db.get_document_by_id = AsyncMock()
    db.delete_document_by_id = AsyncMock()
    db.update_kb_stats = AsyncMock()
    return db


@pytest.fixture
def mock_knowledge_base():
    """Create a mock KnowledgeBase instance using lazy import."""
    from astrbot.core.knowledge_base.models import KnowledgeBase

    kb = KnowledgeBase(
        kb_name="test_kb",
        description="Test knowledge base",
        emoji="test",
        embedding_provider_id="test-embedding-provider",
        rerank_provider_id="test-rerank-provider",
        chunk_size=512,
        chunk_overlap=50,
        top_k_dense=50,
        top_k_sparse=50,
        top_m_final=5,
    )
    return kb


@pytest.fixture
def mock_embedding_provider():
    """Create a mock object that passes isinstance(EmbeddingProvider) checks."""
    from astrbot.core.provider.provider import EmbeddingProvider

    class FakeEmbeddingProvider(EmbeddingProvider):
        def __init__(self) -> None:
            pass

        async def get_embedding(self, text: str) -> list[float]:
            return [0.1, 0.2, 0.3]

        async def get_embeddings(self, text: list[str]) -> list[list[float]]:
            return [[0.1, 0.2, 0.3] for _ in text]

        def get_dim(self) -> int:
            return 3

    return FakeEmbeddingProvider()


@pytest.fixture
def mock_rerank_provider():
    """Create a mock object that passes isinstance(RerankProvider) checks."""
    from astrbot.core.provider.provider import RerankProvider

    class FakeRerankProvider(RerankProvider):
        def __init__(self) -> None:
            pass

        async def rerank_score(self, query: str, documents: list[str]) -> list[float]:
            return [1.0] * len(documents)

    return FakeRerankProvider()


@pytest.fixture
def mock_chunker():
    """Create a mock chunker."""
    chunker = MagicMock()
    chunker.chunk = AsyncMock(return_value=["chunk1", "chunk2"])
    return chunker


@pytest.fixture
def mock_vec_db():
    """Create a mock FaissVecDB."""
    vec_db = MagicMock()
    vec_db.initialize = AsyncMock()
    vec_db.close = AsyncMock()
    vec_db.insert_batch = AsyncMock()
    vec_db.delete = AsyncMock()
    vec_db.count_documents = AsyncMock(return_value=5)
    vec_db.document_storage = MagicMock()
    vec_db.document_storage.get_documents = AsyncMock(return_value=[])
    return vec_db


@pytest.fixture
def helper_kwargs(
    mock_kb_db,
    mock_knowledge_base,
    mock_provider_manager,
    mock_chunker,
):
    """Standard keyword arguments for constructing a KBHelper."""
    return {
        "kb_db": mock_kb_db,
        "kb": mock_knowledge_base,
        "provider_manager": mock_provider_manager,
        "kb_root_dir": "/tmp/test_kb_root",
        "chunker": mock_chunker,
    }


# ---------------------------------------------------------------
# Construction and initialization
# ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_construction_sets_attributes(
    stub_provider_manager_module,
    helper_kwargs,
    mock_kb_db,
    mock_knowledge_base,
    mock_provider_manager,
    mock_chunker,
):
    """Test that KBHelper.__init__ sets all expected attributes."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    helper = KBHelper(
        kb_db=mock_kb_db,
        kb=mock_knowledge_base,
        provider_manager=mock_provider_manager,
        kb_root_dir="/tmp/test_kb_root",
        chunker=mock_chunker,
    )

    assert helper.kb_db is mock_kb_db
    assert helper.kb is mock_knowledge_base
    assert helper.prov_mgr is mock_provider_manager
    assert helper.chunker is mock_chunker
    assert helper.init_error is None
    assert helper.vec_db is None
    assert isinstance(helper.kb_dir, Path)
    assert "medias" in str(helper.kb_medias_dir)
    assert "files" in str(helper.kb_files_dir)


@pytest.mark.asyncio
async def test_initialize_calls_ensure_vec_db(
    stub_provider_manager_module,
    helper_kwargs,
):
    """Test that initialize() delegates to _ensure_vec_db."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    with (
        patch.object(KBHelper, "_ensure_vec_db", new_callable=AsyncMock) as mock_ensure,
    ):
        helper = KBHelper(**helper_kwargs)
        await helper.initialize()

        mock_ensure.assert_awaited_once()


# ---------------------------------------------------------------
# get_ep
# ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_ep_raises_when_no_embedding_provider_id(
    stub_provider_manager_module,
    helper_kwargs,
):
    """Test that get_ep raises ValueError when kb has no embedding_provider_id."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    helper = KBHelper(**helper_kwargs)
    helper.kb.embedding_provider_id = None

    with pytest.raises(ValueError, match="未配置 Embedding Provider"):
        await helper.get_ep()


@pytest.mark.asyncio
async def test_get_ep_raises_when_provider_not_found(
    stub_provider_manager_module,
    helper_kwargs,
):
    """Test that get_ep raises ValueError when provider is not found by id."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    helper_kwargs["provider_manager"].get_provider_by_id.return_value = None
    helper = KBHelper(**helper_kwargs)

    with pytest.raises(ValueError, match="无法找到"):
        await helper.get_ep()


@pytest.mark.asyncio
async def test_get_ep_raises_when_not_embedding_provider(
    stub_provider_manager_module,
    helper_kwargs,
    mock_provider_manager,
):
    """Test that get_ep raises when the returned provider is not EmbeddingProvider."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_provider_manager.get_provider_by_id.return_value = MagicMock()
    helper = KBHelper(**helper_kwargs)

    with pytest.raises(ValueError, match="not an Embedding Provider"):
        await helper.get_ep()


@pytest.mark.asyncio
async def test_get_ep_returns_embedding_provider(
    stub_provider_manager_module,
    helper_kwargs,
    mock_embedding_provider,
    mock_provider_manager,
):
    """Test that get_ep returns the EmbeddingProvider successfully."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_provider_manager.get_provider_by_id.return_value = mock_embedding_provider
    helper = KBHelper(**helper_kwargs)

    result = await helper.get_ep()
    assert result is mock_embedding_provider


# ---------------------------------------------------------------
# get_rp
# ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_rp_returns_none_when_no_rerank_provider_id(
    stub_provider_manager_module,
    helper_kwargs,
):
    """Test that get_rp returns None when kb has no rerank_provider_id."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    helper = KBHelper(**helper_kwargs)
    helper.kb.rerank_provider_id = None

    result = await helper.get_rp()
    assert result is None


@pytest.mark.asyncio
async def test_get_rp_returns_none_when_provider_not_found(
    stub_provider_manager_module,
    helper_kwargs,
    mock_provider_manager,
):
    """Test that get_rp returns None when the provider is not found (logs a warning)."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_provider_manager.get_provider_by_id.return_value = None
    helper = KBHelper(**helper_kwargs)

    result = await helper.get_rp()
    assert result is None


@pytest.mark.asyncio
async def test_get_rp_raises_when_not_rerank_provider(
    stub_provider_manager_module,
    helper_kwargs,
    mock_provider_manager,
):
    """Test that get_rp raises when the returned provider is not RerankProvider."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_provider_manager.get_provider_by_id.return_value = MagicMock()
    helper = KBHelper(**helper_kwargs)

    with pytest.raises(ValueError, match="not a Rerank Provider"):
        await helper.get_rp()


@pytest.mark.asyncio
async def test_get_rp_returns_rerank_provider(
    stub_provider_manager_module,
    helper_kwargs,
    mock_rerank_provider,
    mock_provider_manager,
):
    """Test that get_rp returns the RerankProvider successfully."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_provider_manager.get_provider_by_id.return_value = mock_rerank_provider
    helper = KBHelper(**helper_kwargs)

    result = await helper.get_rp()
    assert result is mock_rerank_provider


# ---------------------------------------------------------------
# _ensure_vec_db
# ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_vec_db_creates_and_initializes(
    stub_provider_manager_module,
    helper_kwargs,
    mock_embedding_provider,
    mock_provider_manager,
    mock_vec_db,
):
    """Test that _ensure_vec_db creates FaissVecDB and initializes it."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_provider_manager.get_provider_by_id.return_value = mock_embedding_provider
    helper = KBHelper(**helper_kwargs)

    with patch(
        "astrbot.core.knowledge_base.kb_helper.FaissVecDB",
        return_value=mock_vec_db,
    ) as mock_faiss_cls:
        result = await helper._ensure_vec_db()

        assert result is mock_vec_db
        assert helper.vec_db is mock_vec_db
        assert helper.init_error is None
        mock_faiss_cls.assert_called_once()
        mock_vec_db.initialize.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_vec_db_clears_stale_init_error(
    stub_provider_manager_module,
    helper_kwargs,
    mock_embedding_provider,
    mock_provider_manager,
    mock_vec_db,
):
    """Test that _ensure_vec_db clears a stale init_error on success."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_provider_manager.get_provider_by_id.return_value = mock_embedding_provider
    helper = KBHelper(**helper_kwargs)
    helper.init_error = "stale error"

    with patch(
        "astrbot.core.knowledge_base.kb_helper.FaissVecDB",
        return_value=mock_vec_db,
    ):
        await helper._ensure_vec_db()
        assert helper.init_error is None


# ---------------------------------------------------------------
# terminate and delete_vec_db
# ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_terminate_closes_vec_db(
    stub_provider_manager_module,
    helper_kwargs,
    mock_vec_db,
):
    """Test that terminate() closes the vec_db."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    helper = KBHelper(**helper_kwargs)
    helper.vec_db = mock_vec_db

    await helper.terminate()
    mock_vec_db.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_terminate_handles_missing_vec_db(
    stub_provider_manager_module,
    helper_kwargs,
):
    """Test that terminate() does not crash when vec_db is None."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    helper = KBHelper(**helper_kwargs)
    helper.vec_db = None

    # Should not raise
    await helper.terminate()


# ---------------------------------------------------------------
# upload_document
# ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_document_with_pre_chunked_text(
    stub_provider_manager_module,
    helper_kwargs,
    mock_kb_db,
    mock_vec_db,
    mock_embedding_provider,
    mock_provider_manager,
):
    """Test that upload_document works with pre-chunked text (skips parsing)."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_provider_manager.get_provider_by_id.return_value = mock_embedding_provider
    helper = KBHelper(**helper_kwargs)

    # Mock the async session for document metadata persistence
    mock_session = MagicMock()
    mock_session.add = MagicMock()
    mock_session.begin = MagicMock()
    mock_session.begin.return_value.__aenter__ = AsyncMock()
    mock_session.begin.return_value.__aexit__ = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_db_ctx = MagicMock()
    mock_db_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_db_ctx.__aexit__ = AsyncMock()
    mock_kb_db.get_db.return_value = mock_db_ctx

    with patch.object(helper, "_get_vec_db", return_value=mock_vec_db):
        doc = await helper.upload_document(
            file_name="test.txt",
            file_content=None,
            file_type="txt",
            pre_chunked_text=["chunk a", "chunk b"],
        )

        assert doc.doc_name == "test.txt"
        assert doc.file_type == "txt"
        # Metadata should have been added
        mock_session.add.assert_called()
        mock_vec_db.insert_batch.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_document_parses_when_no_pre_chunked(
    stub_provider_manager_module,
    helper_kwargs,
    mock_kb_db,
    mock_vec_db,
    mock_embedding_provider,
    mock_provider_manager,
    mock_chunker,
):
    """Test that upload_document parses file content when no pre-chunked text."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_provider_manager.get_provider_by_id.return_value = mock_embedding_provider
    mock_chunker.chunk = AsyncMock(return_value=["parsed chunk"])
    helper = KBHelper(**helper_kwargs)

    mock_session = MagicMock()
    mock_session.add = MagicMock()
    mock_session.begin = MagicMock()
    mock_session.begin.return_value.__aenter__ = AsyncMock()
    mock_session.begin.return_value.__aexit__ = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_db_ctx = MagicMock()
    mock_db_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_db_ctx.__aexit__ = AsyncMock()
    mock_kb_db.get_db.return_value = mock_db_ctx

    mock_parser = MagicMock()
    mock_parse_result = MagicMock()
    mock_parse_result.text = "some parsed text"
    mock_parse_result.media = []
    mock_parser.parse = AsyncMock(return_value=mock_parse_result)

    with (
        patch.object(helper, "_get_vec_db", return_value=mock_vec_db),
        patch(
            "astrbot.core.knowledge_base.kb_helper.select_parser",
            return_value=mock_parser,
        ),
    ):
        doc = await helper.upload_document(
            file_name="test.pdf",
            file_content=b"%PDF-1.4 fake content",
            file_type="pdf",
        )

        assert doc.doc_name == "test.pdf"
        mock_parser.parse.assert_awaited_once()
        mock_chunker.chunk.assert_awaited_once()
        mock_vec_db.insert_batch.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_document_raises_when_no_content_and_no_pre_chunked(
    stub_provider_manager_module,
    helper_kwargs,
    mock_vec_db,
    mock_embedding_provider,
    mock_provider_manager,
):
    """Test that upload_document raises when file_content is None and no pre_chunked."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_provider_manager.get_provider_by_id.return_value = mock_embedding_provider
    helper = KBHelper(**helper_kwargs)

    with (
        patch.object(helper, "_get_vec_db", return_value=mock_vec_db),
        pytest.raises(ValueError, match="file_content 不能为空"),
    ):
        await helper.upload_document(
            file_name="test.pdf",
            file_content=None,
            file_type="pdf",
        )


# ---------------------------------------------------------------
# list_documents / get_document
# ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_documents_delegates_to_db(
    stub_provider_manager_module,
    helper_kwargs,
    mock_kb_db,
):
    """Test that list_documents delegates to kb_db.list_documents_by_kb."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_kb_db.list_documents_by_kb.return_value = ["doc1", "doc2"]
    helper = KBHelper(**helper_kwargs)

    result = await helper.list_documents(offset=0, limit=50)

    mock_kb_db.list_documents_by_kb.assert_awaited_once_with(
        helper.kb.kb_id,
        0,
        50,
    )
    assert result == ["doc1", "doc2"]


@pytest.mark.asyncio
async def test_get_document_delegates_to_db(
    stub_provider_manager_module,
    helper_kwargs,
    mock_kb_db,
):
    """Test that get_document delegates to kb_db.get_document_by_id."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_kb_db.get_document_by_id.return_value = "fake_doc"
    helper = KBHelper(**helper_kwargs)

    result = await helper.get_document("doc-123")

    mock_kb_db.get_document_by_id.assert_awaited_once_with("doc-123")
    assert result == "fake_doc"


# ---------------------------------------------------------------
# delete_document / delete_chunk
# ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_document_delegates_to_db_and_vec_db(
    stub_provider_manager_module,
    helper_kwargs,
    mock_kb_db,
    mock_vec_db,
):
    """Test that delete_document cleans up via kb_db and vec_db."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_kb_db.get_kb_by_id = AsyncMock(return_value=helper_kwargs["kb"])
    helper = KBHelper(**helper_kwargs)
    helper.vec_db = mock_vec_db

    await helper.delete_document("doc-123")

    mock_kb_db.delete_document_by_id.assert_awaited_once_with(
        doc_id="doc-123",
        vec_db=mock_vec_db,
    )
    mock_kb_db.update_kb_stats.assert_awaited()


@pytest.mark.asyncio
async def test_delete_chunk_delegates_to_vec_db(
    stub_provider_manager_module,
    helper_kwargs,
    mock_kb_db,
    mock_vec_db,
):
    """Test that delete_chunk removes a chunk from vec_db and refreshes stats."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_kb_db.get_kb_by_id = AsyncMock(return_value=helper_kwargs["kb"])
    helper = KBHelper(**helper_kwargs)
    helper.vec_db = mock_vec_db

    await helper.delete_chunk("chunk-1", "doc-123")

    mock_vec_db.delete.assert_awaited_once_with("chunk-1")


# ---------------------------------------------------------------
# refresh_kb / refresh_document
# ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_kb_updates_self_kb(
    stub_provider_manager_module,
    helper_kwargs,
    mock_kb_db,
    mock_knowledge_base,
):
    """Test that refresh_kb fetches the latest KB from the database."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    fresh_kb = MagicMock()
    fresh_kb.kb_id = mock_knowledge_base.kb_id
    mock_kb_db.get_kb_by_id = AsyncMock(return_value=fresh_kb)

    helper = KBHelper(**helper_kwargs)

    await helper.refresh_kb()

    mock_kb_db.get_kb_by_id.assert_awaited_once_with(mock_knowledge_base.kb_id)
    assert helper.kb is fresh_kb


@pytest.mark.asyncio
async def test_refresh_document_raises_when_not_found(
    stub_provider_manager_module,
    helper_kwargs,
    mock_kb_db,
):
    """Test that refresh_document raises ValueError when doc does not exist."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_kb_db.get_document_by_id = AsyncMock(return_value=None)
    helper = KBHelper(**helper_kwargs)

    with pytest.raises(ValueError, match="无法找到"):
        await helper.refresh_document("doc-123")


# ---------------------------------------------------------------
# get_chunks_by_doc_id
# ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_chunks_by_doc_id_returns_formatted_chunks(
    stub_provider_manager_module,
    helper_kwargs,
    mock_vec_db,
):
    """Test that get_chunks_by_doc_id returns properly formatted chunks."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_vec_db.document_storage.get_documents.return_value = [
        {
            "doc_id": "chunk-1",
            "metadata": json.dumps(
                {"kb_doc_id": "doc-123", "kb_id": "kb-1", "chunk_index": 0},
            ),
            "text": "chunk content",
        },
    ]
    helper = KBHelper(**helper_kwargs)
    helper.vec_db = mock_vec_db

    result = await helper.get_chunks_by_doc_id("doc-123")

    assert len(result) == 1
    chunk = result[0]
    assert chunk["chunk_id"] == "chunk-1"
    assert chunk["doc_id"] == "doc-123"
    assert chunk["content"] == "chunk content"
    assert chunk["char_count"] == 13


# ---------------------------------------------------------------
# get_chunk_count_by_doc_id
# ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_chunk_count_by_doc_id(
    stub_provider_manager_module,
    helper_kwargs,
    mock_vec_db,
):
    """Test that get_chunk_count_by_doc_id returns the count from vec_db."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_vec_db.count_documents.return_value = 42
    helper = KBHelper(**helper_kwargs)
    helper.vec_db = mock_vec_db

    count = await helper.get_chunk_count_by_doc_id("doc-123")

    assert count == 42
    mock_vec_db.count_documents.assert_awaited_once_with(
        metadata_filter={"kb_doc_id": "doc-123"},
    )


# ---------------------------------------------------------------
# _save_media
# ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_media_creates_media_record(
    stub_provider_manager_module,
    helper_kwargs,
):
    """Test that _save_media saves the media file and returns a KBMedia record."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    helper = KBHelper(**helper_kwargs)

    with patch("astrbot.core.knowledge_base.kb_helper.aiofiles.open") as mock_aiofiles:
        mock_file = AsyncMock()
        mock_aiofiles.return_value.__aenter__ = AsyncMock(return_value=mock_file)
        mock_aiofiles.return_value.__aexit__ = AsyncMock()

        media = await helper._save_media(
            doc_id="doc-1",
            media_type="image",
            file_name="photo.png",
            content=b"fake-image-bytes",
            mime_type="image/png",
        )

        assert media.media_type == "image"
        assert media.file_name == "photo.png"
        assert media.mime_type == "image/png"
        assert media.doc_id == "doc-1"
        mock_file.write.assert_awaited_once_with(b"fake-image-bytes")


# ---------------------------------------------------------------
# upload_from_url
# ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_from_url_raises_when_no_tavily_key(
    stub_provider_manager_module,
    helper_kwargs,
    mock_provider_manager,
):
    """Test that upload_from_url raises when Tavily API key is missing."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_provider_manager.acm.default_conf = {"provider_settings": {}}
    helper = KBHelper(**helper_kwargs)

    with pytest.raises(ValueError, match="Tavily API key"):
        await helper.upload_from_url("http://example.com")


@pytest.mark.asyncio
async def test_upload_from_url_delegates_to_upload_document(
    stub_provider_manager_module,
    helper_kwargs,
    mock_provider_manager,
):
    """Test that upload_from_url extracts text and delegates to upload_document."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_provider_manager.acm.default_conf = {
        "provider_settings": {
            "websearch_tavily_key": ["fake-key"],
        },
    }
    helper = KBHelper(**helper_kwargs)

    with (
        patch(
            "astrbot.core.knowledge_base.kb_helper.extract_text_from_url",
            new_callable=AsyncMock,
            return_value="extracted content",
        ),
        patch.object(
            helper,
            "upload_document",
            new_callable=AsyncMock,
            return_value="fake_doc",
        ),
    ):
        result = await helper.upload_from_url("http://example.com")

        assert result == "fake_doc"


# ---------------------------------------------------------------
# _clean_and_rechunk_content
# ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_clean_and_rechunk_skips_when_not_enabled(
    stub_provider_manager_module,
    helper_kwargs,
    mock_chunker,
):
    """Test that _clean_and_rechunk_content uses chunker directly when cleaning disabled."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_chunker.chunk = AsyncMock(return_value=["chunk a", "chunk b"])
    helper = KBHelper(**helper_kwargs)

    result = await helper._clean_and_rechunk_content(
        content="some text",
        url="http://example.com",
        enable_cleaning=False,
    )

    assert result == ["chunk a", "chunk b"]
    mock_chunker.chunk.assert_awaited_once_with("some text")


@pytest.mark.asyncio
async def test_clean_and_rechunk_skips_when_no_provider_id(
    stub_provider_manager_module,
    helper_kwargs,
    mock_chunker,
):
    """Test that _clean_and_rechunk_content uses chunker when cleaning_provider_id is None."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_chunker.chunk = AsyncMock(return_value=["default chunk"])
    helper = KBHelper(**helper_kwargs)

    result = await helper._clean_and_rechunk_content(
        content="some text",
        url="http://example.com",
        enable_cleaning=True,
        cleaning_provider_id=None,
    )

    assert result == ["default chunk"]


@pytest.mark.asyncio
async def test_clean_and_rechunk_falls_back_on_error(
    stub_provider_manager_module,
    helper_kwargs,
    mock_provider_manager,
    mock_chunker,
):
    """Test that _clean_and_rechunk_content falls back to chunker when LLM call fails."""
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    mock_provider_manager.get_provider_by_id = AsyncMock(
        side_effect=Exception("provider error"),
    )
    mock_chunker.chunk = AsyncMock(return_value=["fallback chunk"])
    helper = KBHelper(**helper_kwargs)

    result = await helper._clean_and_rechunk_content(
        content="some text",
        url="http://example.com",
        enable_cleaning=True,
        cleaning_provider_id="llm-1",
    )

    assert result == ["fallback chunk"]
