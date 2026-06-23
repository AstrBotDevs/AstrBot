from unittest.mock import patch
import pytest
import numpy as np
from astrbot.core.utils.runtime_env import is_faiss_importable
from astrbot.core.db.vec_db.faiss_impl.embedding_storage import EmbeddingStorage

def test_is_faiss_importable():
    res = is_faiss_importable()
    assert isinstance(res, bool)

@pytest.mark.asyncio
async def test_embedding_storage_numpy_fallback(tmp_path):
    # Mock is_faiss_importable to return False
    with patch("astrbot.core.utils.runtime_env.is_faiss_importable", return_value=False):
        path = str(tmp_path / "index.faiss")
        storage = EmbeddingStorage(dimension=4, path=path)
        
        # Verify it fallback to numpy
        assert storage.db_type == "numpy"
        
        # Test insert
        vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        await storage.insert(vec, 42)
        
        assert len(storage._numpy_ids) == 1
        assert storage._numpy_ids[0] == 42
        assert np.array_equal(storage._numpy_vectors[0], vec)
        
        # Test search
        distances, indices = await storage.search(vec, 1)
        assert indices[0, 0] == 42
        assert distances[0, 0] == 0.0
        
        # Test delete
        await storage.delete([42])
        assert len(storage._numpy_ids) == 0
