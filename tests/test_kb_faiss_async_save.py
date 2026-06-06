"""Tests for #5: FAISS save_index uses asyncio.to_thread to avoid blocking
the event loop during synchronous faiss.write_index calls.
"""

import asyncio
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


def _make_storage(dimension: int = 128, path: str = "/tmp/test.index"):
    """Build an EmbeddingStorage instance with a minimal mocked FAISS index."""
    import asyncio

    from astrbot.core.db.vec_db.faiss_impl.embedding_storage import EmbeddingStorage

    storage = EmbeddingStorage.__new__(EmbeddingStorage)
    storage.dimension = dimension
    storage.path = path
    storage._write_lock = asyncio.Lock()
    # Mock FAISS index — just enough to satisfy the method guards
    storage.index = MagicMock()
    storage.index.ntotal = 100
    return storage


class TestFaissSaveIndexAsync:
    """Verify save_index delegates to asyncio.to_thread."""

    @pytest.mark.asyncio
    async def test_save_index_uses_to_thread(self):
        """save_index offloads faiss.write_index to a thread."""
        import faiss  # noqa: F401 — ensure faiss is importable

        storage = _make_storage()

        with patch(
            "astrbot.core.db.vec_db.faiss_impl.embedding_storage.asyncio.to_thread",
        ) as mock_to_thread:
            mock_to_thread.return_value = None  # simulate completion
            await storage.save_index()

        mock_to_thread.assert_awaited_once_with(
            faiss.write_index,
            storage.index,
            storage.path,
        )

    @pytest.mark.asyncio
    async def test_save_index_skips_when_index_none(self):
        """save_index is a no-op when index hasn't been initialized."""
        storage = _make_storage()
        storage.index = None

        with patch(
            "astrbot.core.db.vec_db.faiss_impl.embedding_storage.asyncio.to_thread",
        ) as mock_to_thread:
            await storage.save_index()

        mock_to_thread.assert_not_called()

    @pytest.mark.asyncio
    async def test_insert_calls_save_index(self):
        """insert() calls _save_index_locked after adding the vector."""
        storage = _make_storage()
        storage.index.add_with_ids = MagicMock()

        with patch.object(
            storage, "_save_index_locked", return_value=None
        ) as mock_save:
            vector = np.random.rand(storage.dimension).astype(np.float32)
            await storage.insert(vector, id=42)

        storage.index.add_with_ids.assert_called_once()
        mock_save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_insert_batch_calls_save_index(self):
        """insert_batch() calls _save_index_locked after batch-adding vectors."""
        storage = _make_storage()
        storage.index.add_with_ids = MagicMock()

        with patch.object(
            storage, "_save_index_locked", return_value=None
        ) as mock_save:
            vectors = np.random.rand(10, storage.dimension).astype(np.float32)
            ids = list(range(10))
            await storage.insert_batch(vectors, ids)

        storage.index.add_with_ids.assert_called_once()
        mock_save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_calls_save_index(self):
        """delete() calls _save_index_locked after removing vectors."""
        storage = _make_storage()
        storage.index.remove_ids = MagicMock()

        with patch.object(
            storage, "_save_index_locked", return_value=None
        ) as mock_save:
            await storage.delete([1, 2, 3])

        storage.index.remove_ids.assert_called_once()
        mock_save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_save_index_with_real_faiss_index(self):
        """End-to-end: save_index with a real FAISS index writes to a temp file."""
        import tempfile

        import faiss

        dim = 128
        base_index = faiss.IndexFlatL2(dim)
        index = faiss.IndexIDMap(base_index)
        index.add_with_ids(
            np.random.rand(5, dim).astype(np.float32),
            np.array([1, 2, 3, 4, 5], dtype=np.int64),
        )

        with tempfile.NamedTemporaryFile(suffix=".index", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            storage = _make_storage(dimension=dim, path=tmp_path)
            storage.index = index

            await storage.save_index()

            # Verify file was written and is readable
            assert __import__("os").path.exists(tmp_path)
            assert __import__("os").path.getsize(tmp_path) > 0

            # Round-trip: read back and verify dimension matches
            restored = faiss.read_index(tmp_path)
            assert restored.ntotal == 5
        finally:
            __import__("os").unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_real_save_does_not_block_event_loop(self):
        """Verify a real save_index completes quickly for a small index."""
        import tempfile

        import faiss

        dim = 64
        base_index = faiss.IndexFlatL2(dim)
        index = faiss.IndexIDMap(base_index)
        # 1000 vectors — should be very fast
        index.add_with_ids(
            np.random.rand(1000, dim).astype(np.float32),
            np.arange(1000, dtype=np.int64),
        )

        with tempfile.NamedTemporaryFile(suffix=".index", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            storage = _make_storage(dimension=dim, path=tmp_path)
            storage.index = index

            # Should complete quickly
            await asyncio.wait_for(storage.save_index(), timeout=5.0)
            assert __import__("os").path.getsize(tmp_path) > 0
        finally:
            __import__("os").unlink(tmp_path)
